package io.github.havelroot.processor.cover;

import io.github.havelroot.processor.Palette;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.font.TextAttribute;
import java.awt.geom.Line2D;
import java.awt.geom.Rectangle2D;
import java.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Capa desenhada para documentos sem capa própria (DOCX ou PDF que não pôde ser renderizado):
 * fundo da paleta, rótulo do formato, filete, título em Literata com corpo ajustado e autor no pé.
 */
public final class TypographicCover {

    private static final int BASE_WIDTH = 480;
    private static final int MAX_TITLE_LINES = 5;

    private TypographicCover() {
    }

    public record Rendered(BufferedImage image, Color background) {
    }

    public static Rendered render(String title, String author, String label, int width) {
        String safeTitle = title == null || title.isBlank() ? "Documento sem título" : title.strip();
        Palette.Tone tone = Palette.forKey(safeTitle);
        Color background = tone.color();
        Color ink = Palette.inkFor(background);

        int height = Math.round(width * 4f / 3f);
        float s = width / (float) BASE_WIDTH;
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = image.createGraphics();
        try {
            quality(g);
            g.setColor(background);
            g.fillRect(0, 0, width, height);

            float margin = 44 * s;
            float inset = 16 * s;
            g.setColor(alpha(ink, 0.22f));
            g.setStroke(new BasicStroke(Math.max(1f, 0.8f * s)));
            g.draw(new Rectangle2D.Float(inset, inset, width - 2 * inset, height - 2 * inset));

            Font labelFont = Fonts.SEMIBOLD.deriveFont(Map.of(
                    TextAttribute.SIZE, 11f * s,
                    TextAttribute.TRACKING, 0.28f));
            g.setFont(labelFont);
            g.setColor(alpha(ink, 0.78f));
            float labelBaseline = margin + 12 * s;
            g.drawString(label.toUpperCase(Locale.ROOT), margin, labelBaseline);

            g.setColor(alpha(ink, 0.5f));
            g.setStroke(new BasicStroke(Math.max(1f, 1f * s)));
            float ruleY = labelBaseline + 14 * s;
            g.draw(new Line2D.Float(margin, ruleY, width - margin, ruleY));

            drawTitle(g, safeTitle, ink, margin, height * 0.29f, width - 2 * margin, height * 0.49f, s);

            if (author != null && !author.isBlank()) {
                float authorBaseline = height - margin - 4 * s;
                g.setColor(ink);
                g.setStroke(new BasicStroke(1.4f * s));
                float shortRuleY = authorBaseline - 30 * s;
                g.draw(new Line2D.Float(margin, shortRuleY, margin + 36 * s, shortRuleY));
                g.setFont(Fonts.ITALIC.deriveFont(17f * s));
                g.setColor(alpha(ink, 0.92f));
                g.drawString(ellipsize(author.strip(), g.getFontMetrics(), width - 2 * margin), margin, authorBaseline);
            }
        } finally {
            g.dispose();
        }
        return new Rendered(image, background);
    }

    private static void drawTitle(Graphics2D g, String title, Color ink, float x, float top,
                                  float maxWidth, float maxHeight, float s) {
        float size = 50 * s;
        float minSize = 22 * s;
        List<String> lines;
        float lineHeight;
        while (true) {
            Font font = Fonts.SEMIBOLD.deriveFont(size);
            FontMetrics metrics = g.getFontMetrics(font);
            lines = wrap(title, metrics, maxWidth);
            lineHeight = size * 1.14f;
            boolean fits = lines.size() <= MAX_TITLE_LINES && lines.size() * lineHeight <= maxHeight;
            if (fits || size <= minSize) {
                g.setFont(font);
                break;
            }
            size = Math.max(minSize, size - 1.5f * s);
        }
        if (lines.size() > MAX_TITLE_LINES) {
            List<String> cut = new ArrayList<>(lines.subList(0, MAX_TITLE_LINES));
            String last = cut.get(MAX_TITLE_LINES - 1) + "…";
            cut.set(MAX_TITLE_LINES - 1, ellipsize(last, g.getFontMetrics(), maxWidth));
            lines = cut;
        }
        g.setColor(ink);
        FontMetrics metrics = g.getFontMetrics();
        float baseline = top + metrics.getAscent();
        for (String line : lines) {
            g.drawString(line, x, baseline);
            baseline += lineHeight;
        }
    }

    static List<String> wrap(String text, FontMetrics metrics, float maxWidth) {
        List<String> lines = new ArrayList<>();
        StringBuilder line = new StringBuilder();
        for (String word : text.split("\\s+")) {
            if (word.isEmpty()) {
                continue;
            }
            String candidate = line.isEmpty() ? word : line + " " + word;
            if (metrics.stringWidth(candidate) <= maxWidth) {
                line.setLength(0);
                line.append(candidate);
                continue;
            }
            if (!line.isEmpty()) {
                lines.add(line.toString());
                line.setLength(0);
            }
            String rest = word;
            while (metrics.stringWidth(rest) > maxWidth && rest.length() > 1) {
                int cut = rest.length() - 1;
                while (cut > 1 && metrics.stringWidth(rest.substring(0, cut) + "-") > maxWidth) {
                    cut--;
                }
                lines.add(rest.substring(0, cut) + "-");
                rest = rest.substring(cut);
            }
            line.append(rest);
        }
        if (!line.isEmpty()) {
            lines.add(line.toString());
        }
        return lines;
    }

    private static String ellipsize(String text, FontMetrics metrics, float maxWidth) {
        if (metrics.stringWidth(text) <= maxWidth) {
            return text;
        }
        String base = text.endsWith("…") ? text.substring(0, text.length() - 1) : text;
        while (!base.isEmpty() && metrics.stringWidth(base.strip() + "…") > maxWidth) {
            base = base.substring(0, base.length() - 1);
        }
        return base.strip() + "…";
    }

    private static Color alpha(Color color, float alpha) {
        return new Color(color.getRed(), color.getGreen(), color.getBlue(), Math.round(alpha * 255));
    }

    private static void quality(Graphics2D g) {
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_FRACTIONALMETRICS, RenderingHints.VALUE_FRACTIONALMETRICS_ON);
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE);
    }
}
