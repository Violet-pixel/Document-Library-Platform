package io.github.havelroot.processor.pdf;

import io.github.havelroot.processor.ProcessRequest;
import io.github.havelroot.processor.ProcessResult;
import io.github.havelroot.processor.ProcessingException;
import io.github.havelroot.processor.TextStats;
import io.github.havelroot.processor.cover.CoverWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Calendar;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSBase;
import org.apache.pdfbox.io.IOUtils;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.encryption.InvalidPasswordException;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline.PDDocumentOutline;
import org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline.PDOutlineItem;
import org.apache.pdfbox.text.PDFTextStripper;

/** Lê um PDF com PDFBox: metadados, sumário (marcadores), texto completo e capa. */
public final class PdfExtractor {

    private static final Logger LOG = Logger.getLogger(PdfExtractor.class.getName());
    private static final int MAX_OUTLINE_ITEMS = 2000;
    private static final int MAX_OUTLINE_DEPTH = 8;
    private static final byte[] PDF_MAGIC = "%PDF-".getBytes(java.nio.charset.StandardCharsets.US_ASCII);

    public ProcessResult extract(Path source, Path outputDir, ProcessRequest request) {
        ensureLooksLikePdf(source);
        ProcessResult result = new ProcessResult();
        result.kind = "pdf";
        try (PDDocument document = Loader.loadPDF(source.toFile(), "", IOUtils.createTempFileOnlyStreamCache())) {
            result.encrypted = document.isEncrypted();
            result.pageCount = document.getNumberOfPages();
            if (result.pageCount == 0) {
                throw ProcessingException.corrupt("O PDF não tem nenhuma página.", null);
            }
            readInformation(document, result);
            readPageSize(document, result);
            readOutline(document, result);
            readText(document, result, request.maxTextChars());
            CoverWriter.pdfCover(document, result, outputDir, request.coverWidth(), fallbackTitle(source));
        } catch (InvalidPasswordException e) {
            throw ProcessingException.encrypted("O PDF está protegido por senha e não pode ser aberto.");
        } catch (ProcessingException e) {
            throw e;
        } catch (IOException e) {
            throw ProcessingException.corrupt("Não foi possível ler o PDF: o arquivo está corrompido ou não é um PDF válido.", e);
        }
        return result;
    }

    private static void ensureLooksLikePdf(Path source) {
        // O cabeçalho pode vir depois de lixo no início (permitido até 1024 bytes pela especificação).
        try (InputStream in = Files.newInputStream(source)) {
            byte[] head = in.readNBytes(1024);
            if (indexOf(head, PDF_MAGIC) < 0) {
                throw ProcessingException.corrupt("O arquivo não é um PDF (cabeçalho %PDF ausente).", null);
            }
        } catch (IOException e) {
            throw ProcessingException.corrupt("Não foi possível ler o arquivo.", e);
        }
    }

    private static void readInformation(PDDocument document, ProcessResult result) {
        PDDocumentInformation info = document.getDocumentInformation();
        if (info != null) {
            result.title = cleanTitle(info.getTitle());
            result.author = TextStats.singleLine(info.getAuthor());
            result.subject = TextStats.singleLine(info.getSubject());
            result.keywords = TextStats.singleLine(info.getKeywords());
            result.creator = TextStats.singleLine(info.getCreator());
            result.producer = TextStats.singleLine(info.getProducer());
            result.createdAt = iso(safeDate(info, true));
            result.modifiedAt = iso(safeDate(info, false));
        }
        result.language = TextStats.singleLine(document.getDocumentCatalog().getLanguage());
    }

    /** Datas malformadas no dicionário Info são comuns; nesse caso ficam nulas. */
    private static Calendar safeDate(PDDocumentInformation info, boolean created) {
        try {
            return created ? info.getCreationDate() : info.getModificationDate();
        } catch (RuntimeException e) {
            return null;
        }
    }

    static String cleanTitle(String raw) {
        String title = TextStats.singleLine(raw);
        if (title == null) {
            return null;
        }
        title = title.replaceFirst("^Microsoft (Word|PowerPoint|Excel) - ", "");
        String lower = title.toLowerCase(java.util.Locale.ROOT);
        if (lower.equals("untitled") || lower.equals("sem título") || lower.equals("documento1")) {
            return null;
        }
        return title.isBlank() ? null : title;
    }

    private static void readPageSize(PDDocument document, ProcessResult result) {
        PDPage first = document.getPage(0);
        PDRectangle box = first.getCropBox();
        boolean rotated = first.getRotation() % 180 != 0;
        result.pageWidth = round(rotated ? box.getHeight() : box.getWidth());
        result.pageHeight = round(rotated ? box.getWidth() : box.getHeight());
    }

    private static void readOutline(PDDocument document, ProcessResult result) {
        PDDocumentOutline outline = document.getDocumentCatalog().getDocumentOutline();
        if (outline == null) {
            return;
        }
        Set<COSBase> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        try {
            walk(document, outline.getFirstChild(), 1, result, visited);
        } catch (RuntimeException e) {
            LOG.log(Level.FINE, "Sumário do PDF ignorado", e);
            result.warn("O sumário do PDF está malformado e foi lido só em parte.");
        }
    }

    private static void walk(PDDocument document, PDOutlineItem item, int level, ProcessResult result,
                             Set<COSBase> visited) {
        while (item != null && result.outline.size() < MAX_OUTLINE_ITEMS) {
            if (!visited.add(item.getCOSObject())) {
                result.warn("O sumário do PDF tem uma referência circular.");
                return;
            }
            String title = TextStats.singleLine(item.getTitle());
            if (title != null) {
                result.outline.add(new ProcessResult.OutlineEntry(title, pageNumber(document, item), level, null));
            }
            if (level < MAX_OUTLINE_DEPTH && item.hasChildren()) {
                walk(document, item.getFirstChild(), level + 1, result, visited);
            }
            item = item.getNextSibling();
        }
    }

    private static Integer pageNumber(PDDocument document, PDOutlineItem item) {
        try {
            PDPage page = item.findDestinationPage(document);
            if (page == null) {
                return null;
            }
            int index = document.getPages().indexOf(page);
            return index >= 0 ? index + 1 : null;
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }

    private static void readText(PDDocument document, ProcessResult result, int maxChars) {
        BoundedWriter writer = new BoundedWriter(maxChars + 1024);
        try {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setLineSeparator("\n");
            stripper.setPageEnd("\f");
            stripper.setSortByPosition(false);
            stripper.writeText(document, writer);
        } catch (BoundedWriter.LimitReached e) {
            result.textTruncated = true;
        } catch (IOException | RuntimeException e) {
            LOG.log(Level.FINE, "Falha ao extrair texto", e);
            result.warn("Parte do texto não pôde ser extraída.");
        }
        result.setText(writer.toString(), maxChars);
        if (result.text.replace('\f', ' ').isBlank()) {
            result.warn("O PDF não tem texto selecionável (provavelmente é digitalizado).");
        }
    }

    private static String fallbackTitle(Path source) {
        String name = source.getFileName().toString();
        int dot = name.lastIndexOf('.');
        return (dot > 0 ? name.substring(0, dot) : name).replace('_', ' ').replace('-', ' ');
    }

    private static String iso(Calendar calendar) {
        if (calendar == null) {
            return null;
        }
        return DateTimeFormatter.ISO_INSTANT.format(calendar.toInstant().truncatedTo(ChronoUnit.SECONDS));
    }

    private static Double round(float value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private static int indexOf(byte[] data, byte[] pattern) {
        outer:
        for (int i = 0; i + pattern.length <= data.length; i++) {
            for (int j = 0; j < pattern.length; j++) {
                if (data[i + j] != pattern[j]) {
                    continue outer;
                }
            }
            return i;
        }
        return -1;
    }

    /** Writer que para a extração assim que o limite de caracteres é atingido. */
    static final class BoundedWriter extends Writer {

        static final class LimitReached extends RuntimeException {
            LimitReached() {
                super(null, null, false, false);
            }
        }

        private final StringBuilder buffer = new StringBuilder();
        private final int limit;

        BoundedWriter(int limit) {
            this.limit = limit;
        }

        @Override
        public void write(char[] chars, int offset, int length) {
            int room = limit - buffer.length();
            if (length > room) {
                buffer.append(chars, offset, Math.max(0, room));
                throw new LimitReached();
            }
            buffer.append(chars, offset, length);
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        @Override
        public String toString() {
            return buffer.toString();
        }
    }
}
