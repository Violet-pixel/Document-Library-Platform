package io.github.havelroot.processor.cover;

import io.github.havelroot.processor.Palette;
import io.github.havelroot.processor.ProcessResult;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.apache.pdfbox.pdmodel.PDDocument;

/** Gera cover.jpg na pasta de saída e preenche o campo cover do resultado. */
public final class CoverWriter {

    public static final String FILE_NAME = "cover.jpg";
    private static final Logger LOG = Logger.getLogger(CoverWriter.class.getName());

    private CoverWriter() {
    }

    /** Capa de PDF a partir da página; se a renderização falhar, cai para a capa tipográfica. */
    public static void pdfCover(PDDocument document, ProcessResult result, Path outputDir, int width,
                                String fallbackTitle) {
        try {
            PdfCover.Rendered rendered = PdfCover.render(document, width);
            BufferedImage image = rendered.image();
            write(image, outputDir);
            result.cover = new ProcessResult.Cover(FILE_NAME, image.getWidth(), image.getHeight(),
                    Palette.hex(ImageFiles.averageColor(image)), false);
            if (rendered.pageIndex() > 0) {
                result.warn("A primeira página está em branco; a capa usa a página " + (rendered.pageIndex() + 1) + ".");
            }
        } catch (IOException | RuntimeException e) {
            LOG.log(Level.FINE, "Renderização da capa falhou", e);
            result.warn("Não foi possível desenhar a primeira página; foi gerada uma capa tipográfica.");
            typographic(result, outputDir, width, "PDF", result.title != null ? result.title : fallbackTitle);
        }
    }

    public static void typographic(ProcessResult result, Path outputDir, int width, String label, String title) {
        TypographicCover.Rendered rendered = TypographicCover.render(title, result.author, label, width);
        write(rendered.image(), outputDir);
        result.cover = new ProcessResult.Cover(FILE_NAME, rendered.image().getWidth(), rendered.image().getHeight(),
                Palette.hex(rendered.background()), true);
    }

    private static void write(BufferedImage image, Path outputDir) {
        try {
            ImageFiles.writeJpeg(image, outputDir.resolve(FILE_NAME));
        } catch (IOException e) {
            throw new UncheckedIOException("Não foi possível gravar a capa", e);
        }
    }
}
