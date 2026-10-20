package io.github.havelroot.processor;

/** Falha prevista, já com o status HTTP, o código e a mensagem em português para o cliente. */
public final class ProcessingException extends RuntimeException {

    private final int status;
    private final String code;

    public ProcessingException(int status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public ProcessingException(int status, String code, String message, Throwable cause) {
        super(message, cause);
        this.status = status;
        this.code = code;
    }

    public int status() {
        return status;
    }

    public String code() {
        return code;
    }

    public static ProcessingException badRequest(String message) {
        return new ProcessingException(400, "bad_request", message);
    }

    public static ProcessingException forbidden(String message) {
        return new ProcessingException(403, "forbidden", message);
    }

    public static ProcessingException notFound(String message) {
        return new ProcessingException(404, "not_found", message);
    }

    public static ProcessingException encrypted(String message) {
        return new ProcessingException(422, "encrypted", message);
    }

    public static ProcessingException corrupt(String message, Throwable cause) {
        return new ProcessingException(422, "corrupt", message, cause);
    }

    public static ProcessingException unsupported(String message) {
        return new ProcessingException(422, "unsupported", message);
    }

    public static ProcessingException busy(String message) {
        return new ProcessingException(503, "busy", message);
    }
}
