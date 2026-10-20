package io.github.havelroot.processor.cover;

import java.awt.Font;
import java.awt.FontFormatException;
import java.io.IOException;
import java.io.InputStream;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Literata (SIL OFL 1.1), embutida no jar para a capa sair igual em qualquer máquina. */
final class Fonts {

    private static final Logger LOG = Logger.getLogger(Fonts.class.getName());

    static final Font REGULAR = load("Literata-Regular.ttf", Font.PLAIN);
    static final Font ITALIC = load("Literata-Italic.ttf", Font.ITALIC);
    static final Font SEMIBOLD = load("Literata-SemiBold.ttf", Font.BOLD);

    private Fonts() {
    }

    private static Font load(String file, int fallbackStyle) {
        try (InputStream in = Fonts.class.getResourceAsStream("/fonts/" + file)) {
            if (in == null) {
                throw new IOException("recurso ausente");
            }
            return Font.createFont(Font.TRUETYPE_FONT, in);
        } catch (IOException | FontFormatException e) {
            LOG.log(Level.WARNING, "Fonte " + file + " indisponível, usando a serifa do sistema: " + e.getMessage());
            return new Font(Font.SERIF, fallbackStyle, 12);
        }
    }
}
