package io.github.havelroot.processor;

import java.util.ArrayList;
import java.util.List;

/**
 * Resposta de POST /v1/process. Os nomes dos campos viram snake_case no JSON
 * (pageCount → page_count) e os nulos são mantidos, como no contrato.
 */
public final class ProcessResult {

    public String kind;
    public int pageCount;
    public int wordCount;
    public int charCount;
    public String title;
    public String author;
    public String subject;
    public String keywords;
    public String createdAt;
    public String modifiedAt;
    public String producer;
    public String creator;
    public String language;
    public List<OutlineEntry> outline = new ArrayList<>();
    public String text = "";
    public boolean textTruncated;
    public Cover cover;
    public Html html;
    public Double pageWidth;
    public Double pageHeight;
    public boolean encrypted;
    public List<String> warnings = new ArrayList<>();
    public long elapsedMs;

    public record OutlineEntry(String title, Integer page, int level, String anchor) {
    }

    public record Cover(String file, int width, int height, String color, boolean generated) {
    }

    public record Html(String file, List<String> media) {
    }

    public void setText(String raw, int maxChars) {
        String clean = TextStats.clean(raw);
        if (clean.length() > maxChars) {
            clean = TextStats.truncate(clean, maxChars);
            textTruncated = true;
        }
        text = clean;
        charCount = clean.length();
        wordCount = TextStats.countWords(clean);
    }

    public void warn(String message) {
        if (!warnings.contains(message)) {
            warnings.add(message);
        }
    }
}
