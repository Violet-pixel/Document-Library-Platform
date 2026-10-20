package io.github.havelroot.processor;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.logging.Level;

/** Configuração lida das variáveis de ambiente, com valores padrão seguros. */
public record Config(
        int port,
        Path dataRoot,
        int concurrency,
        int maxTextChars,
        Level logLevel,
        Duration acquireTimeout) {

    public static final int MAX_REQUEST_BYTES = 64 * 1024;

    public static Config fromEnv() {
        return fromMap(System.getenv());
    }

    static Config fromMap(Map<String, String> env) {
        return new Config(
                intValue(env, "PROCESSOR_PORT", 8090, 1, 65535),
                Path.of(env.getOrDefault("PROCESSOR_DATA_ROOT", "/data")).toAbsolutePath().normalize(),
                intValue(env, "PROCESSOR_CONCURRENCY", 2, 1, 64),
                intValue(env, "PROCESSOR_MAX_TEXT_CHARS", 2_000_000, 1_000, 50_000_000),
                level(env.getOrDefault("PROCESSOR_LOG_LEVEL", "INFO")),
                Duration.ofSeconds(intValue(env, "PROCESSOR_ACQUIRE_TIMEOUT", 60, 1, 3600)));
    }

    private static int intValue(Map<String, String> env, String name, int fallback, int min, int max) {
        String raw = env.get(name);
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        try {
            int value = Integer.parseInt(raw.trim());
            if (value < min || value > max) {
                throw new IllegalArgumentException(name + " deve estar entre " + min + " e " + max);
            }
            return value;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(name + " não é um número inteiro: " + raw, e);
        }
    }

    private static Level level(String raw) {
        return switch (raw.trim().toUpperCase()) {
            case "DEBUG", "FINE" -> Level.FINE;
            case "WARN", "WARNING" -> Level.WARNING;
            case "ERROR", "SEVERE" -> Level.SEVERE;
            default -> Level.INFO;
        };
    }
}
