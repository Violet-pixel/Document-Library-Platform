package io.github.havelroot.processor.docx;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/** Relações de uma parte (arquivo .rels): id → tipo e alvo. */
final class Relationships {

    static final String OFFICE_DOCUMENT = "/officeDocument";
    static final String IMAGE = "/image";
    static final String HYPERLINK = "/hyperlink";
    static final String STYLES = "/styles";
    static final String NUMBERING = "/numbering";

    record Relationship(String id, String type, String target, boolean external) {

        boolean is(String typeSuffix) {
            return type != null && type.endsWith(typeSuffix);
        }
    }

    private final Map<String, Relationship> byId = new HashMap<>();

    static Relationships forPart(DocxPackage pkg, String part) throws IOException, XMLStreamException {
        int slash = part.lastIndexOf('/');
        String relsName = (slash >= 0 ? part.substring(0, slash + 1) : "") + "_rels/"
                + (slash >= 0 ? part.substring(slash + 1) : part) + ".rels";
        Relationships rels = new Relationships();
        if (!pkg.has(relsName)) {
            return rels;
        }
        try (InputStream in = pkg.openXml(relsName)) {
            XMLStreamReader reader = Xml.open(in);
            try {
                while (reader.hasNext()) {
                    if (reader.next() == XMLStreamConstants.START_ELEMENT
                            && "Relationship".equals(reader.getLocalName())) {
                        String id = Xml.attr(reader, "Id");
                        if (id != null) {
                            rels.byId.put(id, new Relationship(id, Xml.attr(reader, "Type"),
                                    Xml.attr(reader, "Target"), "External".equalsIgnoreCase(Xml.attr(reader, "TargetMode"))));
                        }
                    }
                }
            } finally {
                reader.close();
            }
        }
        return rels;
    }

    Relationship get(String id) {
        return id == null ? null : byId.get(id);
    }

    Relationship firstOfType(String typeSuffix) {
        return byId.values().stream().filter(r -> r.is(typeSuffix)).findFirst().orElse(null);
    }
}
