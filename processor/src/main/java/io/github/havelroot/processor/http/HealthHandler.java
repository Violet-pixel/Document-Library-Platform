package io.github.havelroot.processor.http;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import io.github.havelroot.processor.Main;
import io.github.havelroot.processor.Metrics;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Semaphore;
import org.apache.pdfbox.util.Version;

/** GET /health: estado, versões e contadores do processador. */
final class HealthHandler implements HttpHandler {

    private final Metrics metrics;
    private final Semaphore slots;
    private final int capacity;

    HealthHandler(Metrics metrics, Semaphore slots, int capacity) {
        this.metrics = metrics;
        this.slots = slots;
        this.capacity = capacity;
    }

    @Override
    public void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"/health".equals(exchange.getRequestURI().getPath())) {
                Responses.error(exchange, 404, "not_found", "Rota inexistente");
                return;
            }
            if (!"GET".equals(exchange.getRequestMethod()) && !"HEAD".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                Responses.error(exchange, 405, "method_not_allowed", "Use GET");
                return;
            }
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("status", "ok");
            body.put("service", "processor");
            body.put("version", Main.VERSION);
            body.put("pdfbox", Version.getVersion());
            body.put("java", Runtime.version().toString());
            body.put("uptime_s", metrics.uptimeSeconds());
            body.put("busy", capacity - slots.availablePermits());
            body.put("capacity", capacity);
            body.put("processed", metrics.processed());
            body.put("failed", metrics.failed());
            body.put("avg_ms", metrics.averageMillis());
            Responses.json(exchange, 200, body);
        }
    }
}
