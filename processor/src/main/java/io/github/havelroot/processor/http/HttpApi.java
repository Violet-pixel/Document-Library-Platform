package io.github.havelroot.processor.http;

import com.sun.net.httpserver.HttpServer;
import io.github.havelroot.processor.Config;
import io.github.havelroot.processor.DocumentProcessor;
import io.github.havelroot.processor.Metrics;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

/** Servidor HTTP embutido do JDK, uma virtual thread por requisição. */
public final class HttpApi {

    private final HttpServer server;
    private final ExecutorService executor;

    public HttpApi(Config config, DocumentProcessor processor, Metrics metrics) throws IOException {
        Semaphore slots = new Semaphore(config.concurrency(), true);
        server = HttpServer.create(new InetSocketAddress(config.port()), 64);
        executor = Executors.newVirtualThreadPerTaskExecutor();
        server.setExecutor(executor);
        server.createContext("/health", new HealthHandler(metrics, slots, config.concurrency()));
        server.createContext("/v1/process", new ProcessHandler(config, processor, metrics, slots));
        server.createContext("/", exchange -> {
            try (exchange) {
                Responses.error(exchange, 404, "not_found", "Rota inexistente");
            }
        });
    }

    public void start() {
        server.start();
    }

    public void stop(int delaySeconds) {
        server.stop(delaySeconds);
        executor.shutdown();
    }
}
