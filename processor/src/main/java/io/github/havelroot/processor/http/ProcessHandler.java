package io.github.havelroot.processor.http;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import io.github.havelroot.processor.Config;
import io.github.havelroot.processor.DocumentProcessor;
import io.github.havelroot.processor.Json;
import io.github.havelroot.processor.Metrics;
import io.github.havelroot.processor.ProcessRequest;
import io.github.havelroot.processor.ProcessResult;
import io.github.havelroot.processor.ProcessingException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

/** POST /v1/process: valida o pedido, espera uma vaga e processa o documento. */
final class ProcessHandler implements HttpHandler {

    private static final Logger LOG = Logger.getLogger(ProcessHandler.class.getName());

    private final Config config;
    private final DocumentProcessor processor;
    private final Metrics metrics;
    private final Semaphore slots;

    ProcessHandler(Config config, DocumentProcessor processor, Metrics metrics, Semaphore slots) {
        this.config = config;
        this.processor = processor;
        this.metrics = metrics;
        this.slots = slots;
    }

    @Override
    public void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            if (!"/v1/process".equals(exchange.getRequestURI().getPath())) {
                Responses.error(exchange, 404, "not_found", "Rota inexistente");
                return;
            }
            if (!"POST".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "POST");
                Responses.error(exchange, 405, "method_not_allowed", "Use POST");
                return;
            }
            ProcessRequest request = null;
            boolean acquired = false;
            try {
                ProcessRequest parsed = ProcessRequest.from(Json.parseObject(readBody(exchange)), config.maxTextChars());
                request = parsed;
                acquired = slots.tryAcquire(config.acquireTimeout().toMillis(), TimeUnit.MILLISECONDS);
                if (!acquired) {
                    throw ProcessingException.busy("O processador está ocupado. Tente de novo em instantes.");
                }
                ProcessResult result = processor.process(request);
                metrics.success(result.elapsedMs);
                LOG.info(() -> String.format("processado kind=%s source=%s paginas=%d palavras=%d avisos=%d ms=%d",
                        result.kind, parsed.source(), result.pageCount, result.wordCount, result.warnings.size(),
                        result.elapsedMs));
                Responses.json(exchange, 200, result);
            } catch (ProcessingException e) {
                if (e.status() == 422 || e.status() == 500) {
                    metrics.failure();
                }
                logFailure(request, e.code(), e.getMessage(), e.status() >= 500 ? e : null);
                Responses.error(exchange, e.status(), e.code(), e.getMessage());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                Responses.error(exchange, 503, "busy", "O processador está sendo encerrado.");
            } catch (RuntimeException | OutOfMemoryError e) {
                metrics.failure();
                logFailure(request, "internal", e.toString(), e);
                Responses.error(exchange, 500, "internal", "Erro interno ao processar o documento.");
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        }
    }

    private static String readBody(HttpExchange exchange) throws IOException {
        try (InputStream in = exchange.getRequestBody()) {
            byte[] bytes = in.readNBytes(Config.MAX_REQUEST_BYTES + 1);
            if (bytes.length > Config.MAX_REQUEST_BYTES) {
                throw ProcessingException.badRequest("O corpo da requisição é grande demais");
            }
            return new String(bytes, StandardCharsets.UTF_8);
        }
    }

    private static void logFailure(ProcessRequest request, String code, String message, Throwable error) {
        String where = request == null ? "" : " kind=" + request.kind().label() + " source=" + request.source();
        LOG.log(error == null ? Level.WARNING : Level.SEVERE,
                "falhou" + where + " erro=" + code + " mensagem=\"" + message + "\"", error);
    }
}
