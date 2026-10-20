package io.github.havelroot.processor.cover;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Iterator;
import java.util.Set;
import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.stream.ImageOutputStream;

/** Gravação de JPEG e estatísticas simples de imagem. */
public final class ImageFiles {

    public static final float JPEG_QUALITY = 0.86f;
    private static final Set<PosixFilePermission> READABLE = PosixFilePermissions.fromString("rw-r--r--");

    private ImageFiles() {
    }

    /** Grava num arquivo temporário e troca de uma vez: quem lê nunca vê uma capa pela metade. */
    public static void writeJpeg(BufferedImage image, Path target) throws IOException {
        BufferedImage rgb = toRgb(image);
        Path temp = Files.createTempFile(target.getParent(), ".cover-", ".tmp");
        try {
            Iterator<ImageWriter> writers = ImageIO.getImageWritersByFormatName("jpeg");
            if (!writers.hasNext()) {
                throw new IOException("Nenhum codificador JPEG disponível");
            }
            ImageWriter writer = writers.next();
            try (ImageOutputStream out = ImageIO.createImageOutputStream(temp.toFile())) {
                ImageWriteParam param = writer.getDefaultWriteParam();
                param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
                param.setCompressionQuality(JPEG_QUALITY);
                param.setProgressiveMode(ImageWriteParam.MODE_DEFAULT);
                writer.setOutput(out);
                writer.write(null, new IIOImage(rgb, null, null), param);
            } finally {
                writer.dispose();
            }
            publish(temp, target);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    /**
     * Arquivos temporários nascem com permissão 600; antes da troca atômica, liberamos leitura
     * para o grupo e os demais, já que a aplicação web serve estes arquivos.
     */
    public static void publish(Path temp, Path target) throws IOException {
        try {
            Files.setPosixFilePermissions(temp, READABLE);
        } catch (UnsupportedOperationException ignored) {
            // sistema de arquivos sem permissões POSIX (Windows): nada a ajustar
        }
        Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }

    public static Color averageColor(BufferedImage image) {
        long r = 0;
        long g = 0;
        long b = 0;
        long count = 0;
        int stepX = Math.max(1, image.getWidth() / 64);
        int stepY = Math.max(1, image.getHeight() / 64);
        for (int y = 0; y < image.getHeight(); y += stepY) {
            for (int x = 0; x < image.getWidth(); x += stepX) {
                int rgb = image.getRGB(x, y);
                r += (rgb >> 16) & 0xff;
                g += (rgb >> 8) & 0xff;
                b += rgb & 0xff;
                count++;
            }
        }
        if (count == 0) {
            return Color.WHITE;
        }
        return new Color((int) (r / count), (int) (g / count), (int) (b / count));
    }

    /** Página "em branco": quase nenhuma variação de luminância numa grade de amostras. */
    public static boolean isNearlyUniform(BufferedImage image) {
        int stepX = Math.max(1, image.getWidth() / 48);
        int stepY = Math.max(1, image.getHeight() / 48);
        double sum = 0;
        double sumSquares = 0;
        int count = 0;
        for (int y = 0; y < image.getHeight(); y += stepY) {
            for (int x = 0; x < image.getWidth(); x += stepX) {
                int rgb = image.getRGB(x, y);
                double lum = 0.299 * ((rgb >> 16) & 0xff) + 0.587 * ((rgb >> 8) & 0xff) + 0.114 * (rgb & 0xff);
                sum += lum;
                sumSquares += lum * lum;
                count++;
            }
        }
        if (count == 0) {
            return true;
        }
        double mean = sum / count;
        double variance = Math.max(0, sumSquares / count - mean * mean);
        return Math.sqrt(variance) < 2.5;
    }

    private static BufferedImage toRgb(BufferedImage image) {
        if (image.getType() == BufferedImage.TYPE_INT_RGB) {
            return image;
        }
        BufferedImage rgb = new BufferedImage(image.getWidth(), image.getHeight(), BufferedImage.TYPE_INT_RGB);
        var g = rgb.createGraphics();
        try {
            g.setColor(Color.WHITE);
            g.fillRect(0, 0, rgb.getWidth(), rgb.getHeight());
            g.drawImage(image, 0, 0, null);
        } finally {
            g.dispose();
        }
        return rgb;
    }
}
