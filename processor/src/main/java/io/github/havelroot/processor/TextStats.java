package io.github.havelroot.processor;

/** Limpeza e contagem de texto extraído. */
public final class TextStats {

    private TextStats() {
    }

    /**
     * Remove caracteres de controle (o PostgreSQL recusa \0 em colunas de texto),
     * padroniza quebras de linha e mantém \n, \t e \f (separador de páginas do PDF).
     */
    public static String clean(String raw) {
        if (raw == null || raw.isEmpty()) {
            return "";
        }
        StringBuilder out = new StringBuilder(raw.length());
        int length = raw.length();
        for (int i = 0; i < length; i++) {
            char c = raw.charAt(i);
            if (c == '\r') {
                out.append('\n');
                if (i + 1 < length && raw.charAt(i + 1) == '\n') {
                    i++;
                }
            } else if (c == '\n' || c == '\t' || c == '\f') {
                out.append(c);
            } else if (c == ' ') {
                out.append(' ');
            } else if (Character.isISOControl(c) || c == '￾' || c == '￿') {
                continue;
            } else if (Character.isHighSurrogate(c)) {
                if (i + 1 < length && Character.isLowSurrogate(raw.charAt(i + 1))) {
                    out.append(c).append(raw.charAt(++i));
                }
            } else if (!Character.isLowSurrogate(c)) {
                out.append(c);
            }
        }
        return out.toString().strip();
    }

    /** Corta sem partir um par substituto (emoji, por exemplo). */
    public static String truncate(String text, int maxChars) {
        if (text.length() <= maxChars) {
            return text;
        }
        int end = maxChars;
        if (end > 0 && Character.isHighSurrogate(text.charAt(end - 1))) {
            end--;
        }
        return text.substring(0, end);
    }

    /** Palavras = sequências de letras ou números, aceitando hífen e apóstrofo internos. */
    public static int countWords(String text) {
        int words = 0;
        boolean inWord = false;
        int length = text.length();
        for (int i = 0; i < length; ) {
            int cp = text.codePointAt(i);
            int size = Character.charCount(cp);
            if (Character.isLetterOrDigit(cp)) {
                if (!inWord) {
                    words++;
                    inWord = true;
                }
            } else if (inWord && (cp == '-' || cp == '\'' || cp == '’') && i + size < length
                    && Character.isLetterOrDigit(text.codePointAt(i + size))) {
                // continua na mesma palavra: "guarda-chuva", "d'água"
            } else {
                inWord = false;
            }
            i += size;
        }
        return words;
    }

    /** Texto curto de uma linha: junta espaços e devolve null se vazio. */
    public static String singleLine(String raw) {
        if (raw == null) {
            return null;
        }
        String value = clean(raw).replaceAll("\\s+", " ").strip();
        return value.isEmpty() ? null : value;
    }
}
