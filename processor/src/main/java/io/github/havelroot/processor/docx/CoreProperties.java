package io.github.havelroot.processor.docx;

import io.github.havelroot.processor.TextStats;
import java.io.IOException;
import java.io.InputStream;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/** docProps/core.xml (título, autor, datas) e docProps/app.xml (páginas, aplicativo). */
final class CoreProperties {

    String title;
    String subject;
    String creator;
    String keywords;
    String description;
    String language;
    String created;
    String modified;
    String application;
    int pages;

    static CoreProperties read(DocxPackage pkg) throws IOException, XMLStreamException {
        CoreProperties props = new CoreProperties();
        if (pkg.has("docProps/core.xml")) {
            try (InputStream in = pkg.openXml("docProps/core.xml")) {
                XMLStreamReader reader = Xml.open(in);
                try {
                    props.parseCore(reader);
                } finally {
                    reader.close();
                }
            }
        }
        if (pkg.has("docProps/app.xml")) {
            try (InputStream in = pkg.openXml("docProps/app.xml")) {
                XMLStreamReader reader = Xml.open(in);
                try {
                    props.parseApp(reader);
                } finally {
                    reader.close();
                }
            }
        }
        return props;
    }

    private void parseCore(XMLStreamReader reader) throws XMLStreamException {
        while (reader.hasNext()) {
            if (reader.next() != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "title" -> title = TextStats.singleLine(Xml.text(reader));
                case "subject" -> subject = TextStats.singleLine(Xml.text(reader));
                case "creator" -> creator = TextStats.singleLine(Xml.text(reader));
                case "keywords" -> keywords = TextStats.singleLine(Xml.text(reader));
                case "description" -> description = TextStats.singleLine(Xml.text(reader));
                case "language" -> language = TextStats.singleLine(Xml.text(reader));
                case "created" -> created = isoDate(Xml.text(reader));
                case "modified" -> modified = isoDate(Xml.text(reader));
                default -> {
                }
            }
        }
    }

    private void parseApp(XMLStreamReader reader) throws XMLStreamException {
        while (reader.hasNext()) {
            if (reader.next() != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "Pages" -> {
                    try {
                        pages = Integer.parseInt(Xml.text(reader).trim());
                    } catch (NumberFormatException e) {
                        pages = 0;
                    }
                }
                case "Application" -> application = TextStats.singleLine(Xml.text(reader));
                default -> {
                }
            }
        }
    }

    /** W3CDTF (2025-03-01T10:00:00Z) para ISO 8601 em UTC, sem frações; null se inválida. */
    static String isoDate(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String value = raw.trim();
        try {
            Instant instant = OffsetDateTime.parse(value).toInstant();
            return DateTimeFormatter.ISO_INSTANT.format(instant.truncatedTo(ChronoUnit.SECONDS));
        } catch (DateTimeParseException e) {
            try {
                return DateTimeFormatter.ISO_INSTANT.format(Instant.parse(value).truncatedTo(ChronoUnit.SECONDS));
            } catch (DateTimeParseException ignored) {
                return null;
            }
        }
    }
}
