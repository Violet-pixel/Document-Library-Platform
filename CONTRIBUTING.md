# Como contribuir com o Lume

Obrigado pelo interesse em ajudar! Este guia resume como preparar o ambiente, propor mudanças e registrar o trabalho feito em dupla.

## Antes de começar

- Procure nas [issues](https://github.com/Violet-pixel/Document-Library-Platform/issues) se o assunto já está sendo discutido.
- Para mudanças grandes, abra uma issue primeiro e descreva a ideia.
- Contribuições para o Lume para Windows ficam no repositório [ravelroot/Document-Library-Desktop](https://github.com/ravelroot/Document-Library-Desktop).

## Ambiente

O jeito mais rápido é com Docker e Docker Compose:

```bash
git clone https://github.com/Violet-pixel/Document-Library-Platform.git
cd Document-Library-Platform
cp .env.example .env            # troque DB_PASSWORD e APP_SECRET_KEY
docker compose up -d --build    # abre em http://localhost:8080
```

No Windows, troque o `cp` por `powershell -ExecutionPolicy Bypass -File scripts\criar-env.ps1`, que cria o `.env` já com senha do banco e chave secreta aleatórias, ou dê dois cliques em `iniciar.cmd`, que faz tudo de uma vez.

Para desenvolver sem Docker você precisa de Python 3.13, Java 21 com Maven, PostgreSQL 16 e Redis 7. Os passos estão na seção [Desenvolvimento e testes](README.md#desenvolvimento-e-testes) do README.

## Fluxo de trabalho

1. Crie uma branch a partir da `main` com um nome curto e descritivo (`corrige-leitor-docx`, `filtro-por-idioma`).
2. Faça commits pequenos, cada um com uma única mudança.
3. Antes de enviar, rode dentro de `web/`:

   ```bash
   ruff check .
   python -m pytest
   python manage.py makemigrations --check --dry-run
   ```

4. Mudou algo visível? Atualize as capturas em `docs/images` e regenere os PDFs.
5. Abra o pull request para a `main` e preencha o template.

O CI compila o processador Java, roda o Ruff e todos os testes e constrói as imagens Docker em cada pull request.

## Mensagens de commit

- Em português, no presente: `Adiciona exportação em BibTeX`, `Corrige capa de DOCX sem título`.
- Primeira linha com até 72 caracteres; se precisar de detalhes, escreva-os depois de uma linha em branco.

## Trabalho em dupla

Quando duas pessoas fizerem a mudança juntas, quem faz o commit adiciona a outra como co-autora no fim da mensagem, depois de uma linha em branco:

```text
Adiciona filtro por idioma

Co-authored-by: Nome da Pessoa <e-mail@exemplo.com>
```

Use o e-mail ligado à conta do GitHub da pessoa (ou o endereço `noreply` que aparece em *Settings → Emails*) para que o commit apareça no perfil dela.

## Estilo de código

O `.editorconfig` define o padrão: UTF-8, fim de linha LF, 4 espaços em Python e Java e 2 em JS, CSS, HTML, JSON e YAML. O Python segue as regras do Ruff configuradas em `web/pyproject.toml`.

## Licença

Ao contribuir, você concorda que sua contribuição será distribuída sob a [licença MIT](LICENSE) do projeto.
