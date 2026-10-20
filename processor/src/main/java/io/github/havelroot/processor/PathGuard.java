package io.github.havelroot.processor;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;

/**
 * Resolve caminhos relativos dentro da raiz de dados e recusa tudo o que escapar dela,
 * seja por "../", caminho absoluto ou link simbólico apontando para fora.
 */
public final class PathGuard {

    private final Path root;

    public PathGuard(Path root) {
        try {
            Files.createDirectories(root);
            this.root = root.toRealPath();
        } catch (IOException e) {
            throw new UncheckedIOException("Não foi possível acessar a raiz de dados " + root, e);
        }
    }

    public Path root() {
        return root;
    }

    /** Arquivo de origem: precisa existir, ser um arquivo comum e estar dentro da raiz. */
    public Path existingFile(String relative, String field) {
        Path path = inside(relative, field);
        if (!Files.exists(path)) {
            throw ProcessingException.notFound("Arquivo não encontrado: " + relative);
        }
        Path real = real(path);
        if (!Files.isRegularFile(real)) {
            throw ProcessingException.notFound("O caminho não é um arquivo: " + relative);
        }
        return real;
    }

    /** Pasta de saída: é criada se não existir e conferida de novo depois de resolvida. */
    public Path outputDirectory(String relative, String field) {
        Path path = inside(relative, field);
        try {
            Files.createDirectories(path);
        } catch (IOException e) {
            throw new UncheckedIOException("Não foi possível criar a pasta de saída " + relative, e);
        }
        Path real = real(path);
        if (!Files.isDirectory(real)) {
            throw ProcessingException.badRequest("O campo " + field + " não aponta para uma pasta");
        }
        return real;
    }

    private Path inside(String relative, String field) {
        if (relative == null || relative.isBlank()) {
            throw ProcessingException.badRequest("O campo " + field + " é obrigatório");
        }
        if (relative.indexOf('\0') >= 0) {
            throw ProcessingException.badRequest("O campo " + field + " contém caracteres inválidos");
        }
        Path candidate;
        try {
            candidate = Path.of(relative);
        } catch (InvalidPathException e) {
            throw ProcessingException.badRequest("O campo " + field + " não é um caminho válido");
        }
        if (candidate.isAbsolute()) {
            throw ProcessingException.forbidden("Use caminhos relativos à pasta de dados em " + field);
        }
        Path resolved = root.resolve(candidate).normalize();
        if (!resolved.startsWith(root)) {
            throw ProcessingException.forbidden("O caminho em " + field + " sai da pasta de dados");
        }
        return resolved;
    }

    private Path real(Path path) {
        try {
            Path real = path.toRealPath();
            if (!real.startsWith(root)) {
                throw ProcessingException.forbidden("O caminho aponta para fora da pasta de dados");
            }
            return real;
        } catch (IOException e) {
            throw ProcessingException.notFound("Caminho inacessível: " + root.relativize(path));
        }
    }
}
