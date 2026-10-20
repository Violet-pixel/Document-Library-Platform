package io.github.havelroot.processor.docx;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/** numbering.xml: diz se o item (numId, nível) é marcador (ul) ou numerado (ol). */
final class Numbering {

    private final Map<Integer, Map<Integer, String>> formatsByAbstract = new HashMap<>();
    private final Map<Integer, Integer> abstractByNum = new HashMap<>();
    private final Map<Integer, Map<Integer, String>> overrides = new HashMap<>();

    static Numbering read(DocxPackage pkg, String part) throws IOException, XMLStreamException {
        Numbering numbering = new Numbering();
        if (part == null || !pkg.has(part)) {
            return numbering;
        }
        try (InputStream in = pkg.openXml(part)) {
            XMLStreamReader reader = Xml.open(in);
            try {
                numbering.parse(reader);
            } finally {
                reader.close();
            }
        }
        return numbering;
    }

    private void parse(XMLStreamReader reader) throws XMLStreamException {
        Integer abstractId = null;
        Integer numId = null;
        Integer level = null;
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                switch (reader.getLocalName()) {
                    case "abstractNum" -> {
                        abstractId = Xml.intAttr(reader, "abstractNumId", -1);
                        numId = null;
                    }
                    case "num" -> {
                        numId = Xml.intAttr(reader, "numId", -1);
                        abstractId = null;
                    }
                    case "abstractNumId" -> {
                        if (numId != null) abstractByNum.put(numId, Xml.intAttr(reader, "val", -1));
                    }
                    case "lvl" -> level = Xml.intAttr(reader, "ilvl", 0);
                    case "lvlOverride" -> level = Xml.intAttr(reader, "ilvl", 0);
                    case "numFmt" -> {
                        String format = Xml.attr(reader, "val");
                        if (format != null && level != null) {
                            if (abstractId != null) {
                                formatsByAbstract.computeIfAbsent(abstractId, k -> new HashMap<>()).put(level, format);
                            } else if (numId != null) {
                                overrides.computeIfAbsent(numId, k -> new HashMap<>()).put(level, format);
                            }
                        }
                    }
                    default -> {
                    }
                }
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                switch (reader.getLocalName()) {
                    case "abstractNum" -> abstractId = null;
                    case "num" -> numId = null;
                    case "lvl", "lvlOverride" -> level = null;
                    default -> {
                    }
                }
            }
        }
    }

    /** true para listas numeradas; marcadores e numeração desconhecida viram lista com marcador. */
    boolean isOrdered(int numId, int level) {
        String format = null;
        for (int lvl = level; lvl >= 0 && format == null; lvl--) {
            format = format(numId, lvl);
        }
        return format != null && !format.equals("bullet") && !format.equals("none");
    }

    private String format(int numId, int level) {
        String format = overrides.getOrDefault(numId, Map.of()).get(level);
        if (format == null) {
            Integer abstractId = abstractByNum.get(numId);
            if (abstractId != null) {
                format = formatsByAbstract.getOrDefault(abstractId, Map.of()).get(level);
            }
        }
        return format;
    }
}
