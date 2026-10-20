package io.github.havelroot.processor;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;
import java.util.Locale;

/** Corpo de POST /v1/process, já validado. */
public record ProcessRequest(String source, Kind kind, String outputDir, int coverWidth, int maxTextChars) {

    public enum Kind {
        PDF, DOCX;

        public String label() {
            return name().toLowerCase(Locale.ROOT);
        }
    }

    static final int DEFAULT_COVER_WIDTH = 480;

    public static ProcessRequest from(JsonObject body, int maxTextCharsLimit) {
        String source = string(body, "source");
        if (source == null || source.isBlank()) {
            throw ProcessingException.badRequest("O campo source é obrigatório");
        }
        Kind kind = kind(string(body, "kind"), source);
        String outputDir = string(body, "output_dir");
        if (outputDir == null || outputDir.isBlank()) {
            int slash = source.replace('\\', '/').lastIndexOf('/');
            outputDir = slash > 0 ? source.substring(0, slash) : ".";
        }
        int coverWidth = integer(body, "cover_width", DEFAULT_COVER_WIDTH, 120, 1600);
        int maxTextChars = integer(body, "max_text_chars", maxTextCharsLimit, 1, maxTextCharsLimit);
        return new ProcessRequest(source, kind, outputDir, coverWidth, maxTextChars);
    }

    private static Kind kind(String raw, String source) {
        String value = raw;
        if (value == null || value.isBlank()) {
            String lower = source.toLowerCase(Locale.ROOT);
            if (lower.endsWith(".pdf")) value = "pdf";
            else if (lower.endsWith(".docx")) value = "docx";
            else throw ProcessingException.badRequest("Informe kind: pdf ou docx");
        }
        return switch (value.trim().toLowerCase(Locale.ROOT)) {
            case "pdf" -> Kind.PDF;
            case "docx" -> Kind.DOCX;
            default -> throw ProcessingException.badRequest("kind deve ser pdf ou docx");
        };
    }

    private static String string(JsonObject body, String name) {
        JsonElement element = body.get(name);
        if (element == null || element.isJsonNull()) {
            return null;
        }
        if (!element.isJsonPrimitive() || !element.getAsJsonPrimitive().isString()) {
            throw ProcessingException.badRequest("O campo " + name + " deve ser texto");
        }
        return element.getAsString();
    }

    private static int integer(JsonObject body, String name, int fallback, int min, int max) {
        JsonElement element = body.get(name);
        if (element == null || element.isJsonNull()) {
            return fallback;
        }
        if (!(element instanceof JsonPrimitive primitive) || !primitive.isNumber()) {
            throw ProcessingException.badRequest("O campo " + name + " deve ser um número inteiro");
        }
        double value = primitive.getAsDouble();
        if (value != Math.rint(value)) {
            throw ProcessingException.badRequest("O campo " + name + " deve ser um número inteiro");
        }
        if (value < min || value > max) {
            throw ProcessingException.badRequest("O campo " + name + " deve estar entre " + min + " e " + max);
        }
        return (int) value;
    }
}
