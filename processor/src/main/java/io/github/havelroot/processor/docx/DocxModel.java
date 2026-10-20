package io.github.havelroot.processor.docx;

import java.util.ArrayList;
import java.util.List;

/** Modelo intermediário do corpo do DOCX, entre a leitura do XML e a escrita do HTML. */
final class DocxModel {

    private DocxModel() {
    }

    sealed interface Block permits Paragraph, Table {
    }

    static final class Paragraph implements Block {
        String styleId;
        Integer outlineLevel;
        Integer numId;
        int ilvl;
        boolean pageBreakBefore;
        final List<Inline> inlines = new ArrayList<>();

        boolean hasVisibleContent() {
            for (Inline inline : inlines) {
                if (inline instanceof Image) return true;
                if (inline instanceof Text text && !text.value().isBlank()) return true;
            }
            return false;
        }

        boolean hasPageBreak() {
            return pageBreakBefore || inlines.stream().anyMatch(i -> i instanceof PageBreak);
        }

        String plainText() {
            StringBuilder out = new StringBuilder();
            for (Inline inline : inlines) {
                if (inline instanceof Text text) out.append(text.value());
                else if (inline instanceof LineBreak) out.append('\n');
            }
            return out.toString();
        }
    }

    static final class Table implements Block {
        final List<Row> rows = new ArrayList<>();
    }

    static final class Row {
        boolean header;
        final List<Cell> cells = new ArrayList<>();
    }

    static final class Cell {
        int gridSpan = 1;
        /** null = sem mesclagem; "restart" inicia, "continue" continua a mesclagem vertical. */
        String verticalMerge;
        final List<Block> blocks = new ArrayList<>();
    }

    record Format(boolean bold, boolean italic, boolean underline, boolean strike, boolean superscript,
                  boolean subscript) {
        static final Format PLAIN = new Format(false, false, false, false, false, false);
    }

    sealed interface Inline permits Text, LineBreak, PageBreak, Image {
    }

    record Text(String value, Format format, String href) implements Inline {
    }

    record LineBreak() implements Inline {
    }

    record PageBreak() implements Inline {
    }

    record Image(String relationshipId, String alt) implements Inline {
    }
}
