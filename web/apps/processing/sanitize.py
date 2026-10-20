"""Higienização do HTML de leitura gerado a partir de DOCX (defesa em profundidade: o processador já gera HTML
restrito, mas o que vai para o navegador passa por uma lista de permissões aqui também)."""

import re

import nh3

TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "sup", "sub",
    "ul", "ol", "li", "blockquote", "table", "thead", "tbody", "tr", "td", "th", "a", "img", "figure",
    "figcaption", "span", "code", "pre",
}
ATTRIBUTES = {
    "*": {"data-b"},
    "h1": {"id"}, "h2": {"id"}, "h3": {"id"}, "h4": {"id"}, "h5": {"id"}, "h6": {"id"},
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "ol": {"start", "type"},
}
SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")media/([A-Za-z0-9_.-]+)"')


def reader_html(raw: str, document_id) -> str:
    raw = SRC_RE.sub(lambda m: f'{m.group(1)}/api/v1/documents/{document_id}/media/{m.group(2)}"', raw)
    return nh3.clean(
        raw,
        tags=TAGS,
        attributes=ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
        strip_comments=True,
        allowed_classes={"p": {"subtitulo"}},
    )
