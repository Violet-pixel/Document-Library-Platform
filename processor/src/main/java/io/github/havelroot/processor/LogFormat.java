package io.github.havelroot.processor;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

/** Uma linha por evento no stdout: "2026-10-20T13:22:01.123Z INFO  mensagem". */
public final class LogFormat extends Formatter {

    @Override
    public String format(LogRecord record) {
        StringBuilder line = new StringBuilder(160)
                .append(Instant.ofEpochMilli(record.getMillis()).truncatedTo(ChronoUnit.MILLIS))
                .append(' ')
                .append(String.format("%-5s", label(record.getLevel())))
                .append(' ')
                .append(formatMessage(record).replace('\n', ' '));
        if (record.getThrown() != null) {
            StringWriter trace = new StringWriter();
            record.getThrown().printStackTrace(new PrintWriter(trace));
            line.append(" | ").append(trace.toString().strip().replace("\n", " | ").replace("\t", ""));
        }
        return line.append(System.lineSeparator()).toString();
    }

    private static String label(Level level) {
        if (level.intValue() >= Level.SEVERE.intValue()) return "ERROR";
        if (level.intValue() >= Level.WARNING.intValue()) return "WARN";
        if (level.intValue() >= Level.INFO.intValue()) return "INFO";
        return "DEBUG";
    }

    public static void install(Level level) {
        Logger root = Logger.getLogger("");
        for (Handler handler : root.getHandlers()) {
            root.removeHandler(handler);
        }
        Handler console = new ConsoleHandler() {
            {
                setOutputStream(System.out);
            }
        };
        console.setFormatter(new LogFormat());
        try {
            console.setEncoding("UTF-8");
        } catch (java.io.UnsupportedEncodingException ignored) {
            // UTF-8 sempre existe na JVM
        }
        console.setLevel(level);
        root.addHandler(console);
        root.setLevel(level);
        // PDFBox e FontBox avisam sobre cada fonte malformada; só erros interessam aqui.
        Logger.getLogger("org.apache.pdfbox").setLevel(Level.SEVERE);
        Logger.getLogger("org.apache.fontbox").setLevel(Level.SEVERE);
    }
}
