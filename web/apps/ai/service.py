"""Descrição de documentos por IA.

Provedores:
- local: resumo extrativo feito aqui mesmo (padrão, não precisa de chave);
- anthropic: API de Mensagens da Anthropic (Claude);
- openai: qualquer API compatível com /v1/chat/completions (OpenAI, Ollama, LM Studio, OpenRouter, Groq...).

Se o provedor externo falhar, a descrição cai para o resumo local e o motivo fica registrado no job.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import httpx
from django.conf import settings

from apps.ai import local

log = logging.getLogger(__name__)

DEFAULT_MODELS = {"anthropic": "claude-haiku-5-5"}
LABELS = {"local": "Resumo automático", "anthropic": "Claude (Anthropic)", "openai": "API compatível com OpenAI"}

SYSTEM_PROMPT = (
    "Você descreve documentos para uma biblioteca digital. Escreva sempre em português do Brasil, com tom neutro e "
    "informativo, e responda apenas com JSON válido."
)

USER_PROMPT = """Leia os dados do documento abaixo e devolva um JSON com dois campos:
- "descricao": de 2 a 3 frases, no máximo 320 caracteres, dizendo do que o documento trata e para quem ele é útil.
  Não comece com "Este documento", não invente informações e não use aspas nem markdown.
- "tags": de 2 a 4 palavras-chave curtas, em minúsculas.

Título: {title}
Autor: {author}
Tipo: {kind}, {pages} páginas
Sumário: {outline}

Trecho do texto:
<<<
{excerpt}
>>>"""


@dataclass
class Description:
    summary: str
    tags: list[str]
    source: str
    model: str = ""
    language: str = ""
    warnings: list[str] = field(default_factory=list)


class ProviderError(Exception):
    pass


def config() -> dict:
    cfg = dict(settings.AI)
    if not cfg["model"]:
        cfg["model"] = DEFAULT_MODELS.get(cfg["provider"], "")
    return cfg


def public_config() -> dict:
    cfg = config()
    provider = cfg["provider"] if cfg["provider"] in LABELS else "local"
    configured = provider == "local" or (
        provider == "anthropic" and bool(cfg["api_key"])
    ) or (provider == "openai" and bool(cfg["model"]))
    return {
        "provider": provider,
        "label": LABELS[provider],
        "model": cfg["model"] if provider != "local" else "",
        "base_url": cfg["base_url"] if provider == "openai" else "",
        "configured": configured,
    }


def build_excerpt(text: str, limit: int, by_line: bool = False) -> str:
    paragraphs = local.clean_text(text, by_line)
    joined = "\n".join(paragraphs)
    if len(joined) <= limit:
        return joined
    head = joined[: int(limit * 0.75)]
    middle_start = len(joined) // 2
    middle = joined[middle_start : middle_start + int(limit * 0.25)]
    return f"{head}\n[...]\n{middle}"


def build_prompt(document, text: str, limit: int) -> str:
    outline = "; ".join(item.get("title", "") for item in (document.outline or [])[:30]) or "não informado"
    return USER_PROMPT.format(
        title=document.title,
        author=document.author or "não informado",
        kind=document.kind.upper(),
        pages=document.page_count or "?",
        outline=outline,
        excerpt=build_excerpt(text, limit, document.kind == "docx"),
    )


def parse_answer(raw: str) -> tuple[str, list[str]]:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ProviderError("A resposta não veio em JSON.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ProviderError(f"JSON inválido na resposta: {exc}") from exc
    summary = str(data.get("descricao") or data.get("description") or "").strip().strip('"')
    if len(summary) < 20:
        raise ProviderError("A descrição veio vazia.")
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[,;\n]", raw_tags)
    elif not isinstance(raw_tags, list):
        raw_tags = []
    tags = [str(t).strip().lower()[:40] for t in raw_tags if str(t).strip()][:4]
    return local.shorten(summary, 420), tags


def call_anthropic(cfg: dict, prompt: str, client: httpx.Client) -> str:
    if not cfg["api_key"]:
        raise ProviderError("AI_API_KEY não definida para o provedor anthropic.")
    base = (cfg["base_url"] or "https://api.anthropic.com").rstrip("/")
    response = client.post(
        f"{base}/v1/messages",
        headers={"x-api-key": cfg["api_key"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": cfg["model"],
            "max_tokens": 500,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    if response.status_code >= 400:
        raise ProviderError(f"Anthropic respondeu {response.status_code}: {response.text[:300]}")
    blocks = response.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def call_openai(cfg: dict, prompt: str, client: httpx.Client) -> str:
    if not cfg["model"]:
        raise ProviderError("Defina AI_MODEL para o provedor openai (ex.: o nome do modelo no OpenAI ou no Ollama).")
    base = (cfg["base_url"] or "https://api.openai.com/v1").rstrip("/")
    headers = {"content-type": "application/json"}
    if cfg["api_key"]:
        headers["authorization"] = f"Bearer {cfg['api_key']}"
    response = client.post(
        f"{base}/chat/completions",
        headers=headers,
        json={
            "model": cfg["model"],
            "temperature": 0.3,
            "max_tokens": 500,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        },
    )
    if response.status_code >= 400:
        raise ProviderError(f"A API respondeu {response.status_code}: {response.text[:300]}")
    choices = response.json().get("choices") or []
    if not choices:
        raise ProviderError("A API não devolveu nenhuma resposta.")
    return choices[0].get("message", {}).get("content", "")


CALLERS = {"anthropic": call_anthropic, "openai": call_openai}


def describe_local(document, text: str, warnings: list[str] | None = None) -> Description:
    headings = [item.get("title", "") for item in (document.outline or [])]
    summary = local.summarize(text, document.title, headings, by_line=document.kind == "docx")
    if not summary:
        summary = f"{document.kind.upper()} sem texto extraível (provavelmente digitalizado como imagem)."
    tags = local.keywords(text, document.title, headings, author=document.author, by_line=document.kind == "docx")
    return Description(summary, tags, "local", "", local.guess_language(text), warnings or [])


def describe(document, text: str, transport: httpx.BaseTransport | None = None) -> Description:
    cfg = config()
    provider = cfg["provider"]
    language = local.guess_language(text)
    if provider not in CALLERS or len(text.strip()) < 200:
        result = describe_local(document, text)
        result.language = language
        return result
    try:
        with httpx.Client(timeout=cfg["timeout"], transport=transport) as client:
            raw = CALLERS[provider](cfg, build_prompt(document, text, cfg["max_input_chars"]), client)
        summary, tags = parse_answer(raw)
        return Description(summary, tags, provider, cfg["model"], language)
    except (ProviderError, httpx.HTTPError, ValueError) as exc:
        log.warning("Provedor %s falhou para %s: %s. Usando o resumo local.", provider, document.id, exc)
        result = describe_local(document, text, [f"{LABELS.get(provider, provider)} falhou: {exc}"])
        result.language = language
        return result
