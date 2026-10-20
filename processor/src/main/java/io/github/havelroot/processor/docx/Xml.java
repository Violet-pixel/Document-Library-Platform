package io.github.havelroot.processor.docx;

import java.io.InputStream;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/** StAX endurecido: sem DTD e sem entidades externas (bloqueia XXE e "billion laughs"). */
final class Xml {

    private static final XMLInputFactory FACTORY = createFactory();

    private Xml() {
    }

    private static XMLInputFactory createFactory() {
        XMLInputFactory factory = XMLInputFactory.newFactory();
        factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        factory.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        factory.setProperty(XMLInputFactory.IS_NAMESPACE_AWARE, true);
        factory.setProperty(XMLInputFactory.IS_COALESCING, true);
        return factory;
    }

    static XMLStreamReader open(InputStream in) throws XMLStreamException {
        return FACTORY.createXMLStreamReader(in);
    }

    /** Atributo pelo nome local, ignorando o prefixo (w:val, r:id, r:embed...). */
    static String attr(XMLStreamReader reader, String localName) {
        for (int i = 0; i < reader.getAttributeCount(); i++) {
            if (localName.equals(reader.getAttributeLocalName(i))) {
                return reader.getAttributeValue(i);
            }
        }
        return null;
    }

    /** Liga/desliga do OOXML: ausente ou qualquer valor diferente de 0/false/off conta como ligado. */
    static boolean toggle(XMLStreamReader reader) {
        String value = attr(reader, "val");
        return value == null || !(value.equals("0") || value.equalsIgnoreCase("false") || value.equalsIgnoreCase("off")
                || value.equalsIgnoreCase("none"));
    }

    static int intAttr(XMLStreamReader reader, String localName, int fallback) {
        String value = attr(reader, localName);
        if (value == null) {
            return fallback;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    /** Avança até o fim do elemento atual (o leitor deve estar num START_ELEMENT). */
    static void skip(XMLStreamReader reader) throws XMLStreamException {
        int depth = 1;
        while (depth > 0 && reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                depth++;
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                depth--;
            }
        }
    }

    /** Texto contido no elemento atual, incluindo filhos; consome até o END_ELEMENT. */
    static String text(XMLStreamReader reader) throws XMLStreamException {
        StringBuilder out = new StringBuilder();
        int depth = 1;
        while (depth > 0 && reader.hasNext()) {
            int event = reader.next();
            switch (event) {
                case XMLStreamConstants.START_ELEMENT -> depth++;
                case XMLStreamConstants.END_ELEMENT -> depth--;
                case XMLStreamConstants.CHARACTERS, XMLStreamConstants.CDATA, XMLStreamConstants.SPACE ->
                        out.append(reader.getText());
                default -> {
                }
            }
        }
        return out.toString();
    }
}
