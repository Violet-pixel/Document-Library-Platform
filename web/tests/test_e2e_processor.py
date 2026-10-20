"""Pipeline completo com o processador Java de verdade.

Rode o processador (`java -jar processor.jar`) com PROCESSOR_DATA_ROOT apontando para a mesma pasta de
E2E_DATA_ROOT e defina PROCESSOR_URL. Sem isso, estes testes são pulados.
"""

import os
from pathlib import Path

import httpx
import pytest

from apps.library.models import Document
from apps.processing import processor, stages

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

URL = os.environ.get("PROCESSOR_URL", "")
ROOT = os.environ.get("E2E_DATA_ROOT", "")


def processor_online() -> bool:
    if not URL or not ROOT:
        return False
    try:
        return httpx.get(f"{URL}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


skip = pytest.mark.skipif(not processor_online(), reason="processador Java não está rodando (PROCESSOR_URL/E2E_DATA_ROOT)")


@pytest.fixture
def shared_root(settings):
    settings.DATA_ROOT = Path(ROOT)
    settings.PROCESSOR_URL = URL
    yield


def run(document_id):
    assert stages.handle("extract", document_id, "e2e").status == "done"
    assert stages.handle("describe", document_id, "e2e").status == "done"
    return Document.objects.get(pk=document_id)


@skip
def test_pdf_end_to_end(api, send, pdf, shared_root):
    item = send(api, "arquitetura.pdf", pdf(pages=4, title="Guia de Arquitetura", author="Equipe Exemplo")).json()
    document = run(item["items"][0]["id"])
    assert document.status == "ready"
    assert document.title == "Guia de Arquitetura" and document.author == "Equipe Exemplo"
    assert document.page_count == 4 and document.word_count > 50
    assert [o["title"] for o in document.outline][:2] == ["Capítulo 1", "Capítulo 2"]
    assert document.cover_path.read_bytes()[:3] == b"\xff\xd8\xff"
    assert document.cover_width == 480 and document.cover_color.startswith("#")
    assert document.summary and document.search_vector
    assert api.get("/api/v1/documents", {"q": "registros de decisao"}).json()["count"] == 1


@skip
def test_docx_end_to_end(api, send, docx_file, shared_root):
    item = send(api, "manual.docx", docx_file("Manual do Colaborador")).json()
    document = run(item["items"][0]["id"])
    assert document.title == "Manual do Colaborador" and document.cover_generated
    reader = api.get(f"/api/v1/documents/{document.id}/reader").json()
    assert "<h" in reader["html"] and "Boas-vindas" in reader["html"]
    assert any(o["title"] == "Boas-vindas" for o in reader["outline"])


@skip
def test_corrupt_pdf_fails_cleanly(api, send, shared_root):
    item = send(api, "quebrado.pdf", b"%PDF-1.7\n" + b"lixo" * 500).json()
    outcome = stages.handle("extract", item["items"][0]["id"], "e2e")
    document = Document.objects.get(pk=item["items"][0]["id"])
    assert outcome.status == "failed" and document.status == "failed" and document.status_detail


@skip
def test_health(shared_root):
    assert processor.health()["online"] is True
