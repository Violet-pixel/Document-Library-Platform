package io.github.havelroot.processor;

import io.github.havelroot.processor.http.HttpApi;
import java.util.logging.Logger;
import javax.imageio.ImageIO;

/** Ponto de entrada do processador de documentos. */
public final class Main {

    public static final String VERSION = "1.0.0";
    private static final Logger LOG = Logger.getLogger(Main.class.getName());

    private Main() {
    }

    public static void main(String[] args) throws Exception {
        Config config;
        try {
            config = Config.fromEnv();
        } catch (IllegalArgumentException e) {
            System.err.println("Configuração inválida: " + e.getMessage());
            System.exit(2);
            return;
        }
        LogFormat.install(config.logLevel());
        System.setProperty("java.awt.headless", "true");
        ImageIO.setUseCache(false);

        PathGuard guard = new PathGuard(config.dataRoot());
        HttpApi api = new HttpApi(config, new DocumentProcessor(guard), new Metrics());
        api.start();
        LOG.info(String.format("Processador %s ouvindo na porta %d · capacidade %d · dados em %s",
                VERSION, config.port(), config.concurrency(), guard.root()));

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            LOG.info("Encerrando o processador");
            api.stop(5);
        }, "encerramento"));
    }
}
