package io.github.havelroot.processor.docx;

import io.github.havelroot.processor.ProcessRequest;
import io.github.havelroot.processor.ProcessResult;
import io.github.havelroot.processor.ProcessingException;
import io.github.havelroot.processor.cover.CoverWriter;
import io.github.havelroot.processor.cover.ImageFiles;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/** Lê um DOCX sem bibliotecas externas: metadados, texto, sumário, HTML de leitura, imagens e capa. */
public final class DocxExtractor {

    public static final String HTML_FILE = "reader.html";
    private static final String MEDIA_DIR = "media";
    private static final Set<String> IMAGE_EXTENSIONS = Set.of("png", "jpg", "jpeg", "gif", "bmp", "webp");
    private static final int WORDS_PER_PAGE = 350;

    public ProcessResult extract(Path source, Path outputDir, ProcessRequest request) {
        ProcessResult result = new ProcessResult();
        result.kind = "docx";
        try (DocxPackage pkg = DocxPackage.open(source)) {
            String mainPart = mainDocumentPart(pkg);
            Relationships relationships = Relationships.forPart(pkg, mainPart);
            Styles styles = Styles.read(pkg, partOf(relationships, mainPart, Relationships.STYLES, "word/styles.xml"));
            Numbering numbering = Numbering.read(pkg,
                    partOf(relationships, mainPart, Relationships.NUMBERING, "word/numbering.xml"));
            CoreProperties properties = CoreProperties.read(pkg);

            DocumentParser parser;
            try (InputStream in = pkg.openXml(mainPart)) {
                XMLStreamReader reader = Xml.open(in);
                try {
                    parser = new DocumentParser(reader, styles, relationships);
                    parser.parse();
                } finally {
                    reader.close();
                }
            }

            Path mediaDir = prepareMediaDirectory(outputDir);
            Media media = new Media(pkg, relationships, mainPart, mediaDir, result);
            HtmlWriter writer = new HtmlWriter(styles, numbering, media::source);
            writer.write(parser.body);
            writeHtml(outputDir.resolve(HTML_FILE), writer.html());
            removeIfEmpty(mediaDir);

            result.setText(writer.text(), request.maxTextChars());
            result.title = first(properties.title, writer.titleText, writer.firstHeading);
            result.author = properties.creator;
            result.subject = properties.subject;
            result.keywords = properties.keywords;
            result.createdAt = properties.created;
            result.modifiedAt = properties.modified;
            result.creator = properties.application;
            result.language = first(properties.language, styles.language());
            result.outline.addAll(writer.outline);
            result.pageWidth = parser.pageWidth;
            result.pageHeight = parser.pageHeight;
            result.pageCount = properties.pages > 0
                    ? properties.pages
                    : Math.max(1, (int) Math.ceil(result.wordCount / (double) WORDS_PER_PAGE));
            result.html = new ProcessResult.Html(HTML_FILE, media.written);
            if (result.text.isBlank()) {
                result.warn("O documento não tem texto.");
            }
            CoverWriter.typographic(result, outputDir, request.coverWidth(), "DOCX",
                    result.title != null ? result.title : fallbackTitle(source));
        } catch (XMLStreamException e) {
            ProcessingException cause = causeOf(e);
            if (cause != null) throw cause;
            throw ProcessingException.corrupt("O DOCX contém XML inválido e não pôde ser lido.", e);
        } catch (IOException e) {
            ProcessingException cause = causeOf(e);
            if (cause != null) throw cause;
            throw ProcessingException.corrupt("O DOCX está corrompido ou incompleto.", e);
        }
        return result;
    }

    private static String mainDocumentPart(DocxPackage pkg) throws IOException, XMLStreamException {
        Relationships root = Relationships.forPart(pkg, "");
        Relationships.Relationship main = root.firstOfType(Relationships.OFFICE_DOCUMENT);
        String part = main != null ? DocxPackage.resolve("", main.target()) : "word/document.xml";
        if (part == null || !pkg.has(part)) {
            throw ProcessingException.corrupt("O arquivo não tem o corpo de um documento do Word (word/document.xml).", null);
        }
        return part;
    }

    private static String partOf(Relationships relationships, String mainPart, String type, String fallback) {
        Relationships.Relationship rel = relationships.firstOfType(type);
        if (rel == null || rel.external()) {
            return fallback;
        }
        String resolved = DocxPackage.resolve(mainPart, rel.target());
        return resolved != null ? resolved : fallback;
    }

    private static Path prepareMediaDirectory(Path outputDir) throws IOException {
        Path mediaDir = outputDir.resolve(MEDIA_DIR);
        if (Files.isSymbolicLink(mediaDir)) {
            throw ProcessingException.forbidden("A pasta media/ de saída não pode ser um link simbólico");
        }
        Files.createDirectories(mediaDir);
        try (DirectoryStream<Path> old = Files.newDirectoryStream(mediaDir)) {
            for (Path file : old) {
                if (Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
                    Files.delete(file);
                }
            }
        }
        return mediaDir;
    }

    private static void removeIfEmpty(Path dir) throws IOException {
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(dir)) {
            if (!entries.iterator().hasNext()) {
                Files.delete(dir);
            }
        }
    }

    private static void writeHtml(Path target, String html) throws IOException {
        Path temp = Files.createTempFile(target.getParent(), ".reader-", ".tmp");
        try {
            Files.writeString(temp, html, StandardCharsets.UTF_8);
            ImageFiles.publish(temp, target);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    private static String first(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) return value;
        }
        return null;
    }

    private static String fallbackTitle(Path source) {
        String name = source.getFileName().toString();
        int dot = name.lastIndexOf('.');
        return (dot > 0 ? name.substring(0, dot) : name).replace('_', ' ').replace('-', ' ');
    }

    private static ProcessingException causeOf(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof ProcessingException processing) return processing;
        }
        return null;
    }

    /** Extrai cada imagem referenciada uma única vez para media/, com nome seguro. */
    private static final class Media {

        private final DocxPackage pkg;
        private final Relationships relationships;
        private final String mainPart;
        private final Path mediaDir;
        private final ProcessResult result;
        private final Map<String, String> byPart = new HashMap<>();
        private final Set<String> usedNames = new HashSet<>();
        final List<String> written = new ArrayList<>();

        Media(DocxPackage pkg, Relationships relationships, String mainPart, Path mediaDir, ProcessResult result) {
            this.pkg = pkg;
            this.relationships = relationships;
            this.mainPart = mainPart;
            this.mediaDir = mediaDir;
            this.result = result;
        }

        String source(String relationshipId) {
            Relationships.Relationship rel = relationships.get(relationshipId);
            if (rel == null) {
                return null;
            }
            if (rel.external()) {
                result.warn("Imagens vinculadas a endereços externos não são carregadas.");
                return null;
            }
            String part = DocxPackage.resolve(mainPart, rel.target());
            if (part == null || !pkg.has(part)) {
                return null;
            }
            String cached = byPart.get(part);
            if (cached != null) {
                return cached;
            }
            String base = part.substring(part.lastIndexOf('/') + 1);
            int dot = base.lastIndexOf('.');
            String extension = dot >= 0 ? base.substring(dot + 1).toLowerCase(Locale.ROOT) : "";
            if (!IMAGE_EXTENSIONS.contains(extension)) {
                result.warn("Imagens em formato " + extension.toUpperCase(Locale.ROOT)
                        + " não podem ser exibidas no navegador e foram omitidas.");
                return null;
            }
            String name = uniqueName(base.substring(0, dot).replaceAll("[^A-Za-z0-9_-]", "_"), extension);
            try {
                pkg.copy(part, mediaDir.resolve(name));
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
            String src = MEDIA_DIR + "/" + name;
            byPart.put(part, src);
            written.add(src);
            return src;
        }

        private String uniqueName(String stem, String extension) {
            String safeStem = stem.isEmpty() ? "imagem" : stem;
            String name = safeStem + "." + extension;
            for (int i = 2; usedNames.contains(name); i++) {
                name = safeStem + "-" + i + "." + extension;
            }
            usedNames.add(name);
            return name;
        }
    }
}
