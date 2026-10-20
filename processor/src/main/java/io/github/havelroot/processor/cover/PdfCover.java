package io.github.havelroot.processor.cover;

import java.awt.image.BufferedImage;
import java.io.IOException;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.rendering.ImageType;
import org.apache.pdfbox.rendering.PDFRenderer;

/** Renderiza a capa de um PDF: a primeira página que não esteja em branco, entre as três primeiras. */
public final class PdfCover {

    private static final int CANDIDATE_PAGES = 3;
    private static final float MAX_SCALE = 6f;
    private static final float MAX_ASPECT = 3f;

    private PdfCover() {
    }

    public record Rendered(BufferedImage image, int pageIndex) {
    }

    public static Rendered render(PDDocument document, int width) throws IOException {
        PDFRenderer renderer = new PDFRenderer(document);
        renderer.setSubsamplingAllowed(true);
        int pages = Math.min(CANDIDATE_PAGES, document.getNumberOfPages());
        Rendered first = null;
        IOException lastError = null;
        for (int index = 0; index < pages; index++) {
            try {
                BufferedImage image = renderPage(renderer, document.getPage(index), index, width);
                Rendered rendered = new Rendered(image, index);
                if (first == null) {
                    first = rendered;
                }
                if (!ImageFiles.isNearlyUniform(image)) {
                    return rendered;
                }
            } catch (IOException | RuntimeException e) {
                lastError = e instanceof IOException io ? io : new IOException(e.getMessage(), e);
            }
        }
        if (first != null) {
            return first;
        }
        throw lastError != null ? lastError : new IOException("O PDF não tem páginas");
    }

    private static BufferedImage renderPage(PDFRenderer renderer, PDPage page, int index, int width)
            throws IOException {
        PDRectangle box = page.getCropBox();
        boolean rotated = page.getRotation() % 180 != 0;
        float pageWidth = rotated ? box.getHeight() : box.getWidth();
        if (pageWidth <= 0) {
            throw new IOException("Página com dimensões inválidas");
        }
        float scale = Math.min(MAX_SCALE, width / pageWidth);
        BufferedImage image = renderer.renderImage(index, scale, ImageType.RGB);
        int maxHeight = Math.round(image.getWidth() * MAX_ASPECT);
        if (image.getHeight() > maxHeight) {
            image = image.getSubimage(0, 0, image.getWidth(), maxHeight);
        }
        return image;
    }
}
