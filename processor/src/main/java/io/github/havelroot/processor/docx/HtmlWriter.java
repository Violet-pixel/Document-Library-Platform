package io.github.havelroot.processor.docx;

import io.github.havelroot.processor.ProcessResult.OutlineEntry;
import io.github.havelroot.processor.TextStats;
import io.github.havelroot.processor.docx.DocxModel.Block;
import io.github.havelroot.processor.docx.DocxModel.Cell;
import io.github.havelroot.processor.docx.DocxModel.Format;
import io.github.havelroot.processor.docx.DocxModel.Image;
import io.github.havelroot.processor.docx.DocxModel.Inline;
import io.github.havelroot.processor.docx.DocxModel.LineBreak;
import io.github.havelroot.processor.docx.DocxModel.Paragraph;
import io.github.havelroot.processor.docx.DocxModel.Row;
import io.github.havelroot.processor.docx.DocxModel.Table;
import io.github.havelroot.processor.docx.DocxModel.Text;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * Converte o modelo do DOCX num fragmento HTML semântico para a tela de leitura,
 * junto com o texto puro (busca e descrição) e o sumário a partir dos títulos.
 */
final class HtmlWriter {

    /** Copia a imagem para a pasta media/ e devolve o src relativo, ou null se não for exibível. */
    interface MediaResolver {
        String source(String relationshipId);
    }

    private enum Kind { NORMAL, TITLE, SUBTITLE, HEADING, QUOTE, LIST }

    private record Classified(Kind kind, int level, boolean ordered) {
    }

    private final Styles styles;
    private final Numbering numbering;
    private final MediaResolver media;

    private final StringBuilder html = new StringBuilder(64 * 1024);
    private final StringBuilder text = new StringBuilder(64 * 1024);
    final List<OutlineEntry> outline = new ArrayList<>();
    String titleText;
    String firstHeading;
    private int blockIndex;
    private int headingCounter;

    HtmlWriter(Styles styles, Numbering numbering, MediaResolver media) {
        this.styles = styles;
        this.numbering = numbering;
        this.media = media;
    }

    String html() {
        return html.toString();
    }

    String text() {
        return text.toString();
    }

    void write(List<Block> blocks) {
        writeBlocks(blocks, true);
    }

    private void writeBlocks(List<Block> blocks, boolean topLevel) {
        ListState lists = new ListState();
        boolean quoteOpen = false;
        boolean lastWasRule = true;
        for (Block block : blocks) {
            if (block instanceof Table table) {
                lists.closeAll();
                quoteOpen = closeQuote(quoteOpen);
                writeTable(table, topLevel);
                lastWasRule = false;
                continue;
            }
            Paragraph paragraph = (Paragraph) block;
            if (paragraph.pageBreakBefore && topLevel && !lastWasRule) {
                lists.closeAll();
                quoteOpen = closeQuote(quoteOpen);
                html.append("<hr").append(blockAttr(true)).append(">\n");
                lastWasRule = true;
            }
            if (paragraph.hasVisibleContent()) {
                Classified kind = classify(paragraph);
                String inline = inlineHtml(paragraph);
                String plain = paragraph.plainText().strip();
                text.append(plain).append('\n');
                switch (kind.kind()) {
                    case LIST -> {
                        quoteOpen = closeQuote(quoteOpen);
                        lists.item(kind.ordered(), kind.level(), inline, topLevel);
                    }
                    case QUOTE -> {
                        lists.closeAll();
                        if (!quoteOpen) {
                            html.append("<blockquote").append(blockAttr(topLevel)).append('>');
                            quoteOpen = true;
                        }
                        html.append("<p>").append(inline).append("</p>");
                    }
                    default -> {
                        lists.closeAll();
                        quoteOpen = closeQuote(quoteOpen);
                        writeParagraph(kind, inline, plain, topLevel);
                    }
                }
                lastWasRule = false;
            }
            boolean breakAfter = paragraph.inlines.stream().anyMatch(i -> i instanceof DocxModel.PageBreak);
            if (breakAfter && topLevel && !lastWasRule) {
                lists.closeAll();
                quoteOpen = closeQuote(quoteOpen);
                html.append("<hr").append(blockAttr(true)).append(">\n");
                lastWasRule = true;
            }
        }
        lists.closeAll();
        closeQuote(quoteOpen);
        if (topLevel) {
            trimTrailingRule();
        }
    }

    private void writeParagraph(Classified kind, String inline, String plain, boolean topLevel) {
        String heading = TextStats.singleLine(plain);
        switch (kind.kind()) {
            case TITLE -> {
                if (titleText == null) titleText = heading;
                String id = "s-" + (++headingCounter);
                html.append("<h1 id=\"").append(id).append('"').append(blockAttr(topLevel)).append('>')
                        .append(inline).append("</h1>\n");
            }
            case HEADING -> {
                if (!topLevel) {
                    html.append("<p><strong>").append(inline).append("</strong></p>");
                    return;
                }
                if (firstHeading == null) firstHeading = heading;
                int level = Math.min(kind.level(), 4);
                int tag = Math.min(level + 1, 4);
                String id = "s-" + (++headingCounter);
                html.append("<h").append(tag).append(" id=\"").append(id).append('"').append(blockAttr(true)).append('>')
                        .append(inline).append("</h").append(tag).append(">\n");
                if (heading != null) {
                    outline.add(new OutlineEntry(heading, null, level, id));
                }
            }
            case SUBTITLE -> html.append("<p class=\"subtitulo\"").append(blockAttr(topLevel)).append('>')
                    .append(inline).append("</p>\n");
            default -> html.append("<p").append(blockAttr(topLevel)).append('>').append(inline).append("</p>\n");
        }
    }

    private boolean closeQuote(boolean open) {
        if (open) {
            html.append("</blockquote>\n");
        }
        return false;
    }

    private void trimTrailingRule() {
        int end = html.length();
        while (end > 0 && Character.isWhitespace(html.charAt(end - 1))) end--;
        int start = html.lastIndexOf("<hr", end);
        if (start >= 0 && html.indexOf(">", start) == end - 1) {
            html.setLength(start);
        }
    }

    private String blockAttr(boolean topLevel) {
        return topLevel ? " data-b=\"" + (blockIndex++) + "\"" : "";
    }

    private Classified classify(Paragraph paragraph) {
        Styles.Role role = styles.role(paragraph.styleId);
        if (role == Styles.Role.TITLE) return new Classified(Kind.TITLE, 0, false);
        if (role == Styles.Role.SUBTITLE) return new Classified(Kind.SUBTITLE, 0, false);
        int heading = paragraph.outlineLevel != null
                ? (paragraph.outlineLevel >= 0 && paragraph.outlineLevel < 9 ? paragraph.outlineLevel + 1 : 0)
                : styles.headingLevel(paragraph.styleId);
        if (heading > 0) return new Classified(Kind.HEADING, heading, false);
        int[] list = paragraph.numId != null
                ? (paragraph.numId > 0 ? new int[]{paragraph.numId, paragraph.ilvl} : null)
                : styles.numbering(paragraph.styleId);
        if (list != null && list[0] > 0) {
            int ilvl = Math.max(0, Math.min(8, list[1]));
            int level = Math.max(ilvl, styles.listLevelFromName(paragraph.styleId));
            return new Classified(Kind.LIST, level, numbering.isOrdered(list[0], ilvl));
        }
        if (role == Styles.Role.QUOTE) return new Classified(Kind.QUOTE, 0, false);
        return new Classified(Kind.NORMAL, 0, false);
    }

    private String inlineHtml(Paragraph paragraph) {
        StringBuilder out = new StringBuilder();
        StringBuilder pending = new StringBuilder();
        Format pendingFormat = null;
        String pendingHref = null;
        for (Inline inline : paragraph.inlines) {
            if (inline instanceof Text run) {
                if (pendingFormat != null && run.format().equals(pendingFormat) && Objects.equals(run.href(), pendingHref)) {
                    pending.append(run.value());
                    continue;
                }
                flush(out, pending, pendingFormat, pendingHref);
                pending.append(run.value());
                pendingFormat = run.format();
                pendingHref = run.href();
                continue;
            }
            flush(out, pending, pendingFormat, pendingHref);
            pendingFormat = null;
            pendingHref = null;
            if (inline instanceof LineBreak) {
                out.append("<br>");
            } else if (inline instanceof Image image) {
                String src = media.source(image.relationshipId());
                if (src != null) {
                    out.append("<img src=\"").append(escape(src)).append("\" alt=\"").append(escape(image.alt()))
                            .append("\" loading=\"lazy\">");
                }
            }
        }
        flush(out, pending, pendingFormat, pendingHref);
        String result = out.toString();
        while (result.endsWith("<br>")) {
            result = result.substring(0, result.length() - 4);
        }
        return result.strip();
    }

    private static void flush(StringBuilder out, StringBuilder pending, Format format, String href) {
        if (pending.isEmpty()) {
            return;
        }
        String content = escape(pending.toString());
        pending.setLength(0);
        if (format == null || content.isBlank()) {
            out.append(content);
            return;
        }
        List<String> tags = new ArrayList<>();
        if (format.bold()) tags.add("strong");
        if (format.italic()) tags.add("em");
        if (format.underline() && href == null) tags.add("u");
        if (format.strike()) tags.add("s");
        if (format.superscript()) tags.add("sup");
        else if (format.subscript()) tags.add("sub");
        if (href != null) {
            out.append("<a href=\"").append(escape(href)).append("\" rel=\"noopener noreferrer\">");
        }
        for (String tag : tags) out.append('<').append(tag).append('>');
        out.append(content);
        for (int i = tags.size() - 1; i >= 0; i--) out.append("</").append(tags.get(i)).append('>');
        if (href != null) {
            out.append("</a>");
        }
    }

    private void writeTable(Table table, boolean topLevel) {
        int rows = table.rows.size();
        List<int[]> columns = new ArrayList<>();
        for (Row row : table.rows) {
            int[] start = new int[row.cells.size()];
            int column = 0;
            for (int i = 0; i < row.cells.size(); i++) {
                start[i] = column;
                column += row.cells.get(i).gridSpan;
            }
            columns.add(start);
        }
        int[][] rowspan = new int[rows][];
        Set<Cell> covered = new HashSet<>();
        for (int r = 0; r < rows; r++) {
            Row row = table.rows.get(r);
            rowspan[r] = new int[row.cells.size()];
            for (int c = 0; c < row.cells.size(); c++) {
                rowspan[r][c] = 1;
                if (!"restart".equals(row.cells.get(c).verticalMerge)) continue;
                for (int below = r + 1; below < rows; below++) {
                    Cell next = cellAt(table.rows.get(below), columns.get(below), columns.get(r)[c]);
                    if (next == null || !"continue".equals(next.verticalMerge)) break;
                    covered.add(next);
                    rowspan[r][c]++;
                }
            }
        }
        html.append("<table").append(blockAttr(topLevel)).append("><tbody>");
        for (int r = 0; r < rows; r++) {
            Row row = table.rows.get(r);
            html.append("<tr>");
            List<String> cellTexts = new ArrayList<>();
            for (int c = 0; c < row.cells.size(); c++) {
                Cell cell = row.cells.get(c);
                if (covered.contains(cell)) continue;
                String tag = row.header ? "th" : "td";
                html.append('<').append(tag);
                if (cell.gridSpan > 1) html.append(" colspan=\"").append(cell.gridSpan).append('"');
                if (rowspan[r][c] > 1) html.append(" rowspan=\"").append(rowspan[r][c]).append('"');
                html.append('>');
                int textMark = text.length();
                writeCell(cell);
                String cellText = text.substring(textMark).strip().replace('\n', ' ');
                text.setLength(textMark);
                cellTexts.add(cellText);
                html.append("</").append(tag).append('>');
            }
            html.append("</tr>");
            text.append(String.join("\t", cellTexts)).append('\n');
        }
        html.append("</tbody></table>\n");
    }

    private void writeCell(Cell cell) {
        if (cell.blocks.size() == 1 && cell.blocks.get(0) instanceof Paragraph only
                && classify(only).kind() == Kind.NORMAL) {
            text.append(only.plainText().strip()).append('\n');
            html.append(inlineHtml(only));
            return;
        }
        writeBlocks(cell.blocks, false);
    }

    private static Cell cellAt(Row row, int[] starts, int column) {
        for (int i = 0; i < starts.length; i++) {
            if (starts[i] == column) return row.cells.get(i);
            if (starts[i] > column) return null;
        }
        return null;
    }

    static String escape(String value) {
        StringBuilder out = new StringBuilder(value.length() + 16);
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '&' -> out.append("&amp;");
                case '<' -> out.append("&lt;");
                case '>' -> out.append("&gt;");
                case '"' -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default -> out.append(c);
            }
        }
        return out.toString();
    }

    /** Listas aninhadas: cada nível aberto mantém um <li> aberto até chegar o próximo item. */
    private final class ListState {

        private final Deque<Boolean> open = new ArrayDeque<>();

        void item(boolean ordered, int level, String content, boolean topLevel) {
            int target = level + 1;
            while (open.size() > target) {
                close();
            }
            if (open.size() == target) {
                html.append("</li>");
                if (open.peek() != ordered) {
                    html.append(open.pop() ? "</ol>" : "</ul>");
                }
            }
            while (open.size() < target) {
                boolean outermost = open.isEmpty();
                html.append(ordered ? "<ol" : "<ul").append(outermost ? blockAttr(topLevel) : "").append('>');
                open.push(ordered);
                if (open.size() < target) {
                    html.append("<li>");
                }
            }
            html.append("<li>").append(content);
        }

        void closeAll() {
            while (!open.isEmpty()) {
                close();
            }
        }

        private void close() {
            html.append("</li>").append(open.pop() ? "</ol>" : "</ul>");
            if (open.isEmpty()) {
                html.append('\n');
            }
        }
    }
}
