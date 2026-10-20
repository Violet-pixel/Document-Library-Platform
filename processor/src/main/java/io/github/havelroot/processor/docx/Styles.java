package io.github.havelroot.processor.docx;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/**
 * Estilos do documento. O Word grava o nome interno dos estilos nativos em inglês ("heading 1")
 * mesmo quando o id está traduzido ("Ttulo1"), por isso a classificação usa o nome.
 */
final class Styles {

    enum Role { NORMAL, TITLE, SUBTITLE, HEADING, QUOTE }

    private static final Pattern NUMBERED_LIST_STYLE = Pattern.compile("^list (?:bullet|number) ([2-9])$");

    private static final class Style {
        String name = "";
        String basedOn;
        Integer outlineLevel;
        Integer numId;
        Integer ilvl;
        Boolean bold;
        Boolean italic;
    }

    private final Map<String, Style> byId = new HashMap<>();
    private String defaultParagraphStyle;
    private String language;

    static Styles read(DocxPackage pkg, String part) throws IOException, XMLStreamException {
        Styles styles = new Styles();
        if (part == null || !pkg.has(part)) {
            return styles;
        }
        try (InputStream in = pkg.openXml(part)) {
            XMLStreamReader reader = Xml.open(in);
            try {
                styles.parse(reader);
            } finally {
                reader.close();
            }
        }
        return styles;
    }

    private void parse(XMLStreamReader reader) throws XMLStreamException {
        Style current = null;
        boolean inDefaults = false;
        boolean inRunProps = false;
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                switch (reader.getLocalName()) {
                    case "docDefaults" -> inDefaults = true;
                    case "style" -> {
                        String id = Xml.attr(reader, "styleId");
                        current = new Style();
                        if (id != null) {
                            byId.put(id, current);
                            String isDefault = Xml.attr(reader, "default");
                            if ("paragraph".equals(Xml.attr(reader, "type")) && isDefault != null && isOn(isDefault)) {
                                defaultParagraphStyle = id;
                            }
                        }
                    }
                    case "name" -> {
                        if (current != null) current.name = lower(Xml.attr(reader, "val"));
                    }
                    case "basedOn" -> {
                        if (current != null) current.basedOn = Xml.attr(reader, "val");
                    }
                    case "outlineLvl" -> {
                        if (current != null) current.outlineLevel = Xml.intAttr(reader, "val", 9);
                    }
                    case "numId" -> {
                        if (current != null) current.numId = Xml.intAttr(reader, "val", 0);
                    }
                    case "ilvl" -> {
                        if (current != null) current.ilvl = Xml.intAttr(reader, "val", 0);
                    }
                    case "rPr" -> inRunProps = true;
                    case "b" -> {
                        if (current != null && inRunProps) current.bold = Xml.toggle(reader);
                    }
                    case "i" -> {
                        if (current != null && inRunProps) current.italic = Xml.toggle(reader);
                    }
                    case "lang" -> {
                        if (inDefaults && language == null) language = Xml.attr(reader, "val");
                    }
                    default -> {
                    }
                }
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                switch (reader.getLocalName()) {
                    case "docDefaults" -> inDefaults = false;
                    case "style" -> current = null;
                    case "rPr" -> inRunProps = false;
                    default -> {
                    }
                }
            }
        }
    }

    String language() {
        return language;
    }

    Role role(String styleId) {
        String name = name(styleId);
        if (name.equals("title")) return Role.TITLE;
        if (name.equals("subtitle")) return Role.SUBTITLE;
        if (name.equals("quote") || name.equals("intense quote")) return Role.QUOTE;
        if (headingLevel(styleId) > 0) return Role.HEADING;
        return Role.NORMAL;
    }

    /** Nível de título 1–9 pelo nome ("heading 2") ou pelo nível de estrutura do estilo; 0 se não for título. */
    int headingLevel(String styleId) {
        Set<String> seen = new HashSet<>();
        String id = styleId == null ? defaultParagraphStyle : styleId;
        while (id != null && seen.add(id)) {
            Style style = byId.get(id);
            if (style == null) {
                break;
            }
            if (style.name.startsWith("heading ")) {
                try {
                    int level = Integer.parseInt(style.name.substring(8).trim());
                    if (level >= 1 && level <= 9) return level;
                } catch (NumberFormatException ignored) {
                    // nome fora do padrão: tenta o nível de estrutura
                }
            }
            if (style.outlineLevel != null) {
                return style.outlineLevel >= 0 && style.outlineLevel < 9 ? style.outlineLevel + 1 : 0;
            }
            id = style.basedOn;
        }
        return 0;
    }

    /** Numeração herdada do estilo (como "List Bullet"), ou null. */
    int[] numbering(String styleId) {
        Set<String> seen = new HashSet<>();
        String id = styleId;
        Integer numId = null;
        Integer ilvl = null;
        while (id != null && seen.add(id)) {
            Style style = byId.get(id);
            if (style == null) break;
            if (numId == null && style.numId != null) numId = style.numId;
            if (ilvl == null && style.ilvl != null) ilvl = style.ilvl;
            id = style.basedOn;
        }
        return numId == null ? null : new int[]{numId, ilvl == null ? 0 : ilvl};
    }

    /**
     * "List Bullet 2", "List Number 3": o nível vem do nome do estilo, já que cada um costuma
     * ter numeração própria no nível 0 e só o recuo indica o aninhamento.
     */
    int listLevelFromName(String styleId) {
        Matcher matcher = NUMBERED_LIST_STYLE.matcher(name(styleId));
        return matcher.matches() ? Integer.parseInt(matcher.group(1)) - 1 : 0;
    }

    /** Estilos de caractere "Strong" e "Emphasis" valem como negrito e itálico. */
    boolean runBold(String styleId) {
        Style style = styleId == null ? null : byId.get(styleId);
        return style != null && (Boolean.TRUE.equals(style.bold) || style.name.equals("strong"));
    }

    boolean runItalic(String styleId) {
        Style style = styleId == null ? null : byId.get(styleId);
        return style != null && (Boolean.TRUE.equals(style.italic) || style.name.equals("emphasis"));
    }

    private String name(String styleId) {
        Style style = byId.get(styleId == null ? (defaultParagraphStyle == null ? "" : defaultParagraphStyle) : styleId);
        return style == null ? "" : style.name;
    }

    private static boolean isOn(String value) {
        return value.equals("1") || value.equalsIgnoreCase("true") || value.equalsIgnoreCase("on");
    }

    private static String lower(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }
}
