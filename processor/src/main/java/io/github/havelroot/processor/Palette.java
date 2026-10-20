package io.github.havelroot.processor;

import java.awt.Color;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.zip.CRC32;

/** A paleta do projeto. As capas geradas usam somente estes tons. */
public final class Palette {

    public record Tone(String name, Color color) {
        public String hex() {
            return Palette.hex(color);
        }
    }

    public static final Tone CREME = tone("Creme", "#F4F1DE");
    public static final Tone CAMURCA = tone("Camurça", "#B0A08C");
    public static final Tone SALVIA = tone("Sálvia", "#B8C9A9");
    public static final Tone ARDOSIA = tone("Ardósia", "#8395A7");
    public static final Tone ROSE = tone("Rosé", "#D8A7B1");
    /** Tons derivados da Ardósia: a paleta não tem cor escura para texto e fundos fortes. */
    public static final Tone ARDOSIA_ESCURA = tone("Ardósia escura", "#4A5A6B");
    public static final Tone TINTA = tone("Tinta", "#2B3540");

    /** Fundos possíveis para as capas tipográficas. */
    public static final List<Tone> ALL = List.of(CREME, CAMURCA, SALVIA, ARDOSIA, ROSE, ARDOSIA_ESCURA);

    private Palette() {
    }

    /** Fundo estável para um título: o mesmo documento sempre recebe a mesma cor. */
    public static Tone forKey(String key) {
        CRC32 crc = new CRC32();
        crc.update((key == null ? "" : key.strip().toLowerCase(Locale.ROOT)).getBytes(StandardCharsets.UTF_8));
        return ALL.get((int) (crc.getValue() % ALL.size()));
    }

    /** Entre Creme e Tinta, a cor de texto com mais contraste sobre o fundo. */
    public static Color inkFor(Color background) {
        double onLight = contrast(background, TINTA.color());
        double onDark = contrast(background, CREME.color());
        return onDark >= onLight ? CREME.color() : TINTA.color();
    }

    public static double contrast(Color a, Color b) {
        double la = luminance(a);
        double lb = luminance(b);
        return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
    }

    public static double luminance(Color color) {
        return 0.2126 * channel(color.getRed()) + 0.7152 * channel(color.getGreen()) + 0.0722 * channel(color.getBlue());
    }

    private static double channel(int value) {
        double c = value / 255.0;
        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    }

    public static String hex(Color color) {
        return String.format("#%02x%02x%02x", color.getRed(), color.getGreen(), color.getBlue());
    }

    private static Tone tone(String name, String hex) {
        return new Tone(name, Color.decode(hex));
    }
}
