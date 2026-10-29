import json

import httpx

from apps.ai import local, service
from apps.library.models import Document

LONG = (
    "Capa\f"
    "O PostgreSQL é um banco de dados relacional de código aberto usado por empresas de todos os tamanhos. "
    "Este material explica como modelar tabelas, criar índices e escrever consultas eficientes. "
    "Os índices aceleram buscas, mas cada índice extra deixa as gravações um pouco mais lentas. "
    "Na prática, a equipe deve medir as consultas antes de criar novos índices no banco de dados.\n\n"
    "Rodapé repetido\f"
    "Transações garantem que um conjunto de operações aconteça por inteiro ou não aconteça. "
    "O PostgreSQL usa controle de concorrência multiversão para que leituras não bloqueiem gravações. "
    "Backups regulares e testes de restauração completam a rotina de cuidado com o banco de dados.\n"
    "Rodapé repetido\f"
    "Consultas lentas podem ser analisadas com EXPLAIN ANALYZE, que mostra o plano escolhido pelo banco. "
    "Rodapé repetido\fRodapé repetido"
)


def doc(**kwargs):
    defaults = dict(title="Introdução ao PostgreSQL", author="", kind="pdf", page_count=5, outline=[])
    defaults.update(kwargs)
    return Document(**defaults)


def test_local_summary_is_short_and_relevant():
    summary = local.summarize(LONG, "Introdução ao PostgreSQL", ["Índices", "Transações"])
    assert 60 < len(summary) <= 360
    assert "PostgreSQL" in summary
    assert "Rodapé" not in summary and "Capa" not in summary


def test_language_and_keywords():
    assert local.guess_language(LONG) == "pt"
    assert local.guess_language("The quick brown fox jumps over the lazy dog and the cat " * 5) == "en"
    tags = local.keywords(LONG, "Introdução ao PostgreSQL")
    assert "postgresql" in tags and len(tags) <= 4


def test_sentence_split_keeps_abbreviations():
    parts = local.split_sentences("O Dr. Silva chegou cedo. Ele trouxe o relatório pág. 4 completo. Fim da reunião.")
    assert parts[0] == "O Dr. Silva chegou cedo."
    assert len(parts) == 3


def test_hyphenated_lines_are_joined():
    text = (
        "A equipe revisou o plano de migração e separou um docu-\n"
        "mento importante para a reunião de quinta-feira, com os\n"
        "riscos de cada etapa e os responsáveis por cada tarefa.\n"
        "Próximos passos\n"
        "Cada responsável deve atualizar o quadro até sexta-feira à tarde.\n"
    )
    assert local.clean_text(text) == [
        "A equipe revisou o plano de migração e separou um documento importante para a reunião de quinta-feira, "
        "com os riscos de cada etapa e os responsáveis por cada tarefa.",
        "Cada responsável deve atualizar o quadro até sexta-feira à tarde.",
    ]


def answer(text):
    return json.dumps({"descricao": text, "tags": ["Banco de Dados", "sql", "índices"]})


def test_anthropic_provider(settings):
    settings.AI = {**settings.AI, "provider": "anthropic", "api_key": "chave-teste", "model": ""}
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        reply = answer("Guia introdutório ao PostgreSQL para quem modela tabelas e escreve consultas no dia a dia.")
        return httpx.Response(200, json={"content": [{"type": "text", "text": reply}]})

    result = service.describe(doc(), LONG, transport=httpx.MockTransport(handler))
    assert result.source == "anthropic" and result.model == "claude-haiku-5-5"
    assert result.summary.startswith("Guia introdutório") and result.tags == ["banco de dados", "sql", "índices"]
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "chave-teste" and seen["headers"]["anthropic-version"] == "2023-06-01"
    assert "Introdução ao PostgreSQL" in seen["body"]["messages"][0]["content"]


def test_openai_compatible_provider(settings):
    settings.AI = {**settings.AI, "provider": "openai", "api_key": "", "model": "llama3.2", "base_url": "http://ollama:11434/v1"}

    def handler(request: httpx.Request):
        assert str(request.url) == "http://ollama:11434/v1/chat/completions"
        assert "authorization" not in request.headers
        reply = "Claro! " + answer("Material de estudo sobre PostgreSQL com foco em índices, transações e backups.")
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    result = service.describe(doc(), LONG, transport=httpx.MockTransport(handler))
    assert result.source == "openai" and result.model == "llama3.2"
    assert result.summary.startswith("Material de estudo")


def test_provider_failure_falls_back_to_local(settings):
    settings.AI = {**settings.AI, "provider": "anthropic", "api_key": "x"}
    transport = httpx.MockTransport(lambda request: httpx.Response(529, json={"error": "overloaded"}))
    result = service.describe(doc(), LONG, transport=transport)
    assert result.source == "local" and result.summary
    assert "529" in result.warnings[0]


def test_invalid_json_falls_back(settings):
    settings.AI = {**settings.AI, "provider": "openai", "model": "m"}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "sem json"}}]}))
    assert service.describe(doc(), LONG, transport=transport).source == "local"


def test_tags_as_text_are_split():
    summary = "Guia de PostgreSQL com exemplos de consultas, índices e transações."
    _, tags = service.parse_answer(json.dumps({"descricao": summary, "tags": "PostgreSQL, SQL; índices"}))
    assert tags == ["postgresql", "sql", "índices"]
    _, tags = service.parse_answer(json.dumps({"descricao": summary, "tags": 3}))
    assert tags == []


def test_public_config_never_exposes_key(settings):
    settings.AI = {**settings.AI, "provider": "anthropic", "api_key": "segredo-123"}
    config = service.public_config()
    assert "segredo-123" not in json.dumps(config)
    assert config["configured"] is True and config["label"] == "Claude (Anthropic)"


def test_scanned_document_without_text(settings):
    result = service.describe(doc(), "   ")
    assert "sem texto" in result.summary
