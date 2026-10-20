package io.github.havelroot.processor.docx;

import io.github.havelroot.processor.ProcessingException;
import io.github.havelroot.processor.cover.ImageFiles;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Enumeration;
import java.util.zip.ZipEntry;
import java.util.zip.ZipException;
import java.util.zip.ZipFile;

/**
 * O pacote OOXML (um zip). Toda leitura passa por um contador de bytes descompactados,
 * então um "zip bomb" é interrompido antes de ocupar memória ou disco.
 */
final class DocxPackage implements AutoCloseable {

    static final int MAX_ENTRIES = 10_000;
    static final long MAX_XML_BYTES = 64L * 1024 * 1024;
    static final long MAX_MEDIA_BYTES = 50L * 1024 * 1024;
    static final long MAX_TOTAL_BYTES = 512L * 1024 * 1024;

    private static final byte[] ZIP_MAGIC = {0x50, 0x4B, 0x03, 0x04};
    private static final byte[] OLE_MAGIC = {(byte) 0xD0, (byte) 0xCF, 0x11, (byte) 0xE0};
    private static final byte[] ENCRYPTION_INFO = "EncryptionInfo".getBytes(StandardCharsets.UTF_16LE);

    private final ZipFile zip;
    private long totalRead;

    private DocxPackage(ZipFile zip) {
        this.zip = zip;
    }

    static DocxPackage open(Path file) {
        byte[] head = readHead(file);
        if (startsWith(head, OLE_MAGIC)) {
            if (containsEncryptionInfo(file)) {
                throw ProcessingException.encrypted("O DOCX está protegido por senha e não pode ser aberto.");
            }
            throw ProcessingException.unsupported(
                    "Arquivos .doc do Word 97-2003 não são suportados. Abra no Word e salve como .docx.");
        }
        if (!startsWith(head, ZIP_MAGIC)) {
            throw ProcessingException.corrupt("O arquivo não é um DOCX válido.", null);
        }
        ZipFile zip;
        try {
            zip = new ZipFile(file.toFile(), StandardCharsets.UTF_8);
        } catch (ZipException e) {
            throw ProcessingException.corrupt("O DOCX está corrompido (zip inválido).", e);
        } catch (IOException e) {
            throw ProcessingException.corrupt("Não foi possível abrir o DOCX.", e);
        }
        if (zip.size() > MAX_ENTRIES) {
            closeQuietly(zip);
            throw ProcessingException.corrupt("O DOCX tem arquivos internos demais para ser processado com segurança.", null);
        }
        DocxPackage pkg = new DocxPackage(zip);
        if (!pkg.has("[Content_Types].xml")) {
            pkg.close();
            throw ProcessingException.corrupt("O arquivo não é um documento do Word (falta [Content_Types].xml).", null);
        }
        return pkg;
    }

    boolean has(String name) {
        return zip.getEntry(name) != null;
    }

    /** Fluxo limitado de uma parte XML; feche depois de usar. */
    InputStream openXml(String name) throws IOException {
        return open(name, MAX_XML_BYTES);
    }

    void copy(String name, Path target) throws IOException {
        Path temp = Files.createTempFile(target.getParent(), ".media-", ".tmp");
        try (InputStream in = open(name, MAX_MEDIA_BYTES)) {
            Files.copy(in, temp, StandardCopyOption.REPLACE_EXISTING);
            ImageFiles.publish(temp, target);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    Enumeration<? extends ZipEntry> entries() {
        return zip.entries();
    }

    private InputStream open(String name, long maxBytes) throws IOException {
        ZipEntry entry = zip.getEntry(name);
        if (entry == null || entry.isDirectory()) {
            throw new IOException("Parte ausente no DOCX: " + name);
        }
        return new LimitedStream(zip.getInputStream(entry), name, maxBytes);
    }

    /**
     * Resolve o alvo de uma relação (relativo à pasta da parte de origem) para o nome dentro do zip.
     * Devolve null se o caminho tentar sair do pacote.
     */
    static String resolve(String sourcePart, String target) {
        if (target == null || target.isBlank()) {
            return null;
        }
        String base = sourcePart.contains("/") ? sourcePart.substring(0, sourcePart.lastIndexOf('/') + 1) : "";
        String combined = target.startsWith("/") ? target.substring(1) : base + target;
        Deque<String> parts = new ArrayDeque<>();
        for (String part : combined.split("/")) {
            if (part.isEmpty() || part.equals(".")) {
                continue;
            }
            if (part.equals("..")) {
                if (parts.isEmpty()) {
                    return null;
                }
                parts.removeLast();
            } else {
                parts.addLast(part);
            }
        }
        return String.join("/", parts);
    }

    @Override
    public void close() {
        closeQuietly(zip);
    }

    private static byte[] readHead(Path file) {
        try (InputStream in = Files.newInputStream(file)) {
            return in.readNBytes(8);
        } catch (IOException e) {
            throw ProcessingException.corrupt("Não foi possível ler o arquivo.", e);
        }
    }

    /** Arquivos Office criptografados são contêineres OLE com o fluxo "EncryptionInfo". */
    private static boolean containsEncryptionInfo(Path file) {
        try (InputStream in = Files.newInputStream(file)) {
            byte[] data = in.readNBytes(32 * 1024 * 1024);
            outer:
            for (int i = 0; i + ENCRYPTION_INFO.length <= data.length; i++) {
                for (int j = 0; j < ENCRYPTION_INFO.length; j++) {
                    if (data[i + j] != ENCRYPTION_INFO[j]) {
                        continue outer;
                    }
                }
                return true;
            }
            return false;
        } catch (IOException e) {
            return false;
        }
    }

    private static boolean startsWith(byte[] data, byte[] prefix) {
        if (data.length < prefix.length) {
            return false;
        }
        for (int i = 0; i < prefix.length; i++) {
            if (data[i] != prefix[i]) {
                return false;
            }
        }
        return true;
    }

    private static void closeQuietly(ZipFile zip) {
        try {
            zip.close();
        } catch (IOException ignored) {
            // nada a fazer: o arquivo só estava sendo lido
        }
    }

    private final class LimitedStream extends FilterInputStream {

        private final String name;
        private final long maxBytes;
        private long read;

        LimitedStream(InputStream in, String name, long maxBytes) {
            super(in);
            this.name = name;
            this.maxBytes = maxBytes;
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value >= 0) {
                count(1);
            }
            return value;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            int n = super.read(buffer, offset, length);
            if (n > 0) {
                count(n);
            }
            return n;
        }

        private void count(int n) {
            read += n;
            totalRead += n;
            if (read > maxBytes || totalRead > MAX_TOTAL_BYTES) {
                throw ProcessingException.corrupt(
                        "O DOCX excede os limites de segurança ao descompactar " + name + " (possível zip bomb).", null);
            }
        }
    }
}
