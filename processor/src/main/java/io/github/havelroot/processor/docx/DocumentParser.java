package io.github.havelroot.processor.docx;

import io.github.havelroot.processor.docx.DocxModel.Block;
import io.github.havelroot.processor.docx.DocxModel.Cell;
import io.github.havelroot.processor.docx.DocxModel.Format;
import io.github.havelroot.processor.docx.DocxModel.Image;
import io.github.havelroot.processor.docx.DocxModel.LineBreak;
import io.github.havelroot.processor.docx.DocxModel.PageBreak;
import io.github.havelroot.processor.docx.DocxModel.Paragraph;
import io.github.havelroot.processor.docx.DocxModel.Row;
import io.github.havelroot.processor.docx.DocxModel.Table;
import io.github.havelroot.processor.docx.DocxModel.Text;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

/**
 * Lê word/document.xml. Regra de todos os métodos parse*: são chamados com o leitor no
 * START_ELEMENT do elemento e devolvem com ele no END_ELEMENT correspondente.
 */
final class DocumentParser {

    private final XMLStreamReader reader;
    private final Styles styles;
    private final Relationships relationships;
    final List<Block> body = new ArrayList<>();
    Double pageWidth;
    Double pageHeight;

    DocumentParser(XMLStreamReader reader, Styles styles, Relationships relationships) {
        this.reader = reader;
        this.styles = styles;
        this.relationships = relationships;
    }

    void parse() throws XMLStreamException {
        while (reader.hasNext()) {
            if (reader.next() == XMLStreamConstants.START_ELEMENT && "body".equals(reader.getLocalName())) {
                parseBlocks(body, null);
                return;
            }
        }
    }

    private void parseBlocks(List<Block> out, Cell cell) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "p" -> out.add(parseParagraph());
                case "tbl" -> out.add(parseTable());
                case "sdt", "sdtContent", "customXml", "smartTag", "ins", "AlternateContent", "Choice" ->
                        parseBlocks(out, cell);
                case "tcPr" -> {
                    if (cell != null) parseCellProperties(cell);
                    else Xml.skip(reader);
                }
                case "sectPr" -> parseSection();
                default -> Xml.skip(reader);
            }
        }
    }

    private Paragraph parseParagraph() throws XMLStreamException {
        Paragraph paragraph = new Paragraph();
        parseParagraphContent(paragraph, null);
        return paragraph;
    }

    private void parseParagraphContent(Paragraph paragraph, String href) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "pPr" -> parseParagraphProperties(paragraph);
                case "r" -> parseRun(paragraph, href, new Format[]{Format.PLAIN});
                case "hyperlink" -> parseParagraphContent(paragraph, hyperlink(Xml.attr(reader, "id")));
                case "ins", "smartTag", "customXml", "fldSimple", "sdt", "sdtContent", "AlternateContent", "Choice",
                     "dir", "bdo", "moveTo" -> parseParagraphContent(paragraph, href);
                default -> Xml.skip(reader);
            }
        }
    }

    private void parseParagraphProperties(Paragraph paragraph) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "pStyle" -> {
                    paragraph.styleId = Xml.attr(reader, "val");
                    Xml.skip(reader);
                }
                case "numPr" -> parseNumbering(paragraph);
                case "outlineLvl" -> {
                    paragraph.outlineLevel = Xml.intAttr(reader, "val", 9);
                    Xml.skip(reader);
                }
                case "pageBreakBefore" -> {
                    paragraph.pageBreakBefore = Xml.toggle(reader);
                    Xml.skip(reader);
                }
                default -> Xml.skip(reader);
            }
        }
    }

    private void parseNumbering(Paragraph paragraph) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "ilvl" -> paragraph.ilvl = Math.max(0, Math.min(8, Xml.intAttr(reader, "val", 0)));
                case "numId" -> paragraph.numId = Xml.intAttr(reader, "val", 0);
                default -> {
                }
            }
            Xml.skip(reader);
        }
    }

    /** Conteúdo de um w:r; também serve para mc:AlternateContent/mc:Choice dentro do run. */
    private void parseRun(Paragraph paragraph, String href, Format[] format) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "rPr" -> format[0] = parseRunProperties();
                case "t" -> paragraph.inlines.add(new Text(Xml.text(reader), format[0], href));
                case "tab", "ptab" -> {
                    paragraph.inlines.add(new Text(" ", format[0], href));
                    Xml.skip(reader);
                }
                case "noBreakHyphen" -> {
                    paragraph.inlines.add(new Text("-", format[0], href));
                    Xml.skip(reader);
                }
                case "br" -> {
                    String type = Xml.attr(reader, "type");
                    paragraph.inlines.add("page".equals(type) ? new PageBreak() : new LineBreak());
                    Xml.skip(reader);
                }
                case "cr" -> {
                    paragraph.inlines.add(new LineBreak());
                    Xml.skip(reader);
                }
                case "drawing" -> parseDrawing(paragraph);
                case "pict", "object" -> parseVml(paragraph);
                case "AlternateContent", "Choice" -> parseRun(paragraph, href, format);
                default -> Xml.skip(reader);
            }
        }
    }

    private Format parseRunProperties() throws XMLStreamException {
        boolean bold = false;
        boolean italic = false;
        boolean underline = false;
        boolean strike = false;
        boolean superscript = false;
        boolean subscript = false;
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                break;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "b" -> bold = Xml.toggle(reader);
                case "i" -> italic = Xml.toggle(reader);
                case "u" -> underline = Xml.toggle(reader);
                case "strike", "dstrike" -> strike = strike || Xml.toggle(reader);
                case "vertAlign" -> {
                    String value = Xml.attr(reader, "val");
                    superscript = "superscript".equals(value);
                    subscript = "subscript".equals(value);
                }
                case "rStyle" -> {
                    String style = Xml.attr(reader, "val");
                    bold = bold || styles.runBold(style);
                    italic = italic || styles.runItalic(style);
                }
                default -> {
                }
            }
            Xml.skip(reader);
        }
        return new Format(bold, italic, underline, strike, superscript, subscript);
    }

    /** Imagem DrawingML: o r:embed do a:blip e a descrição (alt) do wp:docPr. */
    private void parseDrawing(Paragraph paragraph) throws XMLStreamException {
        String embed = null;
        String alt = null;
        int depth = 1;
        while (depth > 0 && reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                depth++;
                switch (reader.getLocalName()) {
                    case "docPr" -> {
                        String description = Xml.attr(reader, "descr");
                        alt = description != null && !description.isBlank() ? description : Xml.attr(reader, "title");
                    }
                    case "blip" -> {
                        if (embed == null) embed = Xml.attr(reader, "embed");
                    }
                    default -> {
                    }
                }
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                depth--;
            }
        }
        if (embed != null) {
            paragraph.inlines.add(new Image(embed, alt == null ? "" : alt.strip()));
        }
    }

    /** Imagem VML antiga (w:pict): v:imagedata com r:id. */
    private void parseVml(Paragraph paragraph) throws XMLStreamException {
        String id = null;
        String alt = null;
        int depth = 1;
        while (depth > 0 && reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.START_ELEMENT) {
                depth++;
                if ("imagedata".equals(reader.getLocalName()) && id == null) {
                    id = Xml.attr(reader, "id");
                    alt = Xml.attr(reader, "title");
                } else if ("shape".equals(reader.getLocalName()) && alt == null) {
                    alt = Xml.attr(reader, "alt");
                }
            } else if (event == XMLStreamConstants.END_ELEMENT) {
                depth--;
            }
        }
        if (id != null) {
            paragraph.inlines.add(new Image(id, alt == null ? "" : alt.strip()));
        }
    }

    private Table parseTable() throws XMLStreamException {
        Table table = new Table();
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return table;
            }
            if (event == XMLStreamConstants.START_ELEMENT) {
                if ("tr".equals(reader.getLocalName())) {
                    table.rows.add(parseRow());
                } else {
                    Xml.skip(reader);
                }
            }
        }
        return table;
    }

    private Row parseRow() throws XMLStreamException {
        Row row = new Row();
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return row;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "trPr" -> parseRowProperties(row);
                case "tc" -> {
                    Cell cell = new Cell();
                    parseBlocks(cell.blocks, cell);
                    row.cells.add(cell);
                }
                default -> Xml.skip(reader);
            }
        }
        return row;
    }

    private void parseRowProperties(Row row) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event == XMLStreamConstants.START_ELEMENT) {
                if ("tblHeader".equals(reader.getLocalName())) {
                    row.header = Xml.toggle(reader);
                }
                Xml.skip(reader);
            }
        }
    }

    private void parseCellProperties(Cell cell) throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event != XMLStreamConstants.START_ELEMENT) {
                continue;
            }
            switch (reader.getLocalName()) {
                case "gridSpan" -> cell.gridSpan = Math.max(1, Math.min(64, Xml.intAttr(reader, "val", 1)));
                case "vMerge" -> {
                    String value = Xml.attr(reader, "val");
                    cell.verticalMerge = value == null ? "continue" : value.toLowerCase(Locale.ROOT);
                }
                default -> {
                }
            }
            Xml.skip(reader);
        }
    }

    private void parseSection() throws XMLStreamException {
        while (reader.hasNext()) {
            int event = reader.next();
            if (event == XMLStreamConstants.END_ELEMENT) {
                return;
            }
            if (event == XMLStreamConstants.START_ELEMENT) {
                if ("pgSz".equals(reader.getLocalName()) && pageWidth == null) {
                    int width = Xml.intAttr(reader, "w", 0);
                    int height = Xml.intAttr(reader, "h", 0);
                    if (width > 0 && height > 0) {
                        pageWidth = width / 20.0;
                        pageHeight = height / 20.0;
                    }
                }
                Xml.skip(reader);
            }
        }
    }

    /** Só links externos http(s) e mailto viram <a>; âncoras internas ficam como texto. */
    private String hyperlink(String relationshipId) {
        Relationships.Relationship rel = relationships.get(relationshipId);
        if (rel == null || !rel.external() || rel.target() == null) {
            return null;
        }
        String target = rel.target().strip();
        String lower = target.toLowerCase(Locale.ROOT);
        if (lower.startsWith("http://") || lower.startsWith("https://") || lower.startsWith("mailto:")) {
            return target;
        }
        return null;
    }
}
