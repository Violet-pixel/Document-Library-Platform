package io.github.havelroot.processor;

import io.github.havelroot.processor.docx.DocxExtractor;
import io.github.havelroot.processor.pdf.PdfExtractor;
import java.nio.file.Path;

/** Resolve os caminhos com segurança e despacha para o extrator do formato. */
public final class DocumentProcessor {

    private final PathGuard guard;
    private final PdfExtractor pdf = new PdfExtractor();
    private final DocxExtractor docx = new DocxExtractor();

    public DocumentProcessor(PathGuard guard) {
        this.guard = guard;
    }

    public ProcessResult process(ProcessRequest request) {
        long started = System.nanoTime();
        Path source = guard.existingFile(request.source(), "source");
        Path outputDir = guard.outputDirectory(request.outputDir(), "output_dir");
        ProcessResult result = switch (request.kind()) {
            case PDF -> pdf.extract(source, outputDir, request);
            case DOCX -> docx.extract(source, outputDir, request);
        };
        result.elapsedMs = (System.nanoTime() - started) / 1_000_000;
        return result;
    }
}
