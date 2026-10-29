import pytest

from apps.core import redis as r
from apps.library.models import Collection, Document
from apps.processing import queue

pytestmark = pytest.mark.django_db(transaction=True)


def test_upload_pdf_stores_file_and_queues(api, user, pdf, send, settings):
    response = send(api, "guia_de_arquitetura.pdf", pdf())
    assert response.status_code == 201, response.content
    item = response.json()["items"][0]
    assert item["kind"] == "pdf" and item["status"] == "queued" and item["duplicate"] is False
    assert item["title"] == "Guia de arquitetura"
    document = Document.objects.get(pk=item["id"])
    assert document.file_path.read_bytes().startswith(b"%PDF")
    assert document.owner == user and len(document.sha256) == 64
    assert r.client().xlen(queue.EXTRACT) == 1


def test_upload_docx_is_detected_by_content(api, docx_file, send):
    response = send(api, "manual.docx", docx_file())
    assert response.json()["items"][0]["kind"] == "docx"


def test_duplicate_is_not_stored_twice(api, pdf, send):
    content = pdf()
    first = send(api, "a.pdf", content).json()["items"][0]
    second = send(api, "copia.pdf", content).json()["items"][0]
    assert second["duplicate"] is True and second["id"] == first["id"]
    assert Document.objects.count() == 1


def test_same_file_for_different_users(api, other, api_for, pdf, send):
    content = pdf()
    send(api, "a.pdf", content)
    assert send(api_for(other), "a.pdf", content).json()["items"][0]["duplicate"] is False
    assert Document.objects.count() == 2


@pytest.mark.parametrize(
    "name,content,message",
    [
        ("falso.pdf", b"isto nao e um pdf", "não corresponde"),
        ("antigo.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100, ".doc antigos"),
        ("notas.txt", b"texto simples", "Formato não suportado"),
        ("vazio.pdf", b"", "vazio"),
        ("zip.docx", b"PK\x03\x04quebrado", "corrompido"),
    ],
)
def test_invalid_files_are_rejected(api, send, name, content, message):
    response = send(api, name, content)
    assert response.status_code == 400
    assert message in response.json()["errors"][0]["message"]
    assert Document.objects.count() == 0


def test_partial_success_reports_errors(api, pdf, send):
    from django.core.files.uploadedfile import SimpleUploadedFile

    files = [SimpleUploadedFile("bom.pdf", pdf()), SimpleUploadedFile("ruim.pdf", b"nada")]
    response = api.post("/api/v1/documents", {"files": files}, format="multipart")
    body = response.json()
    assert response.status_code == 201
    assert len(body["items"]) == 1 and body["errors"][0]["file"] == "ruim.pdf"


def test_size_limit(api, pdf, send, settings):
    settings.MAX_UPLOAD_MB = 0
    response = send(api, "grande.pdf", pdf())
    assert "limite" in response.json()["errors"][0]["message"]
    assert not list((settings.DATA_ROOT / "tmp").glob("*.part"))


def test_upload_into_collection_with_visibility(api, user, pdf, send):
    collection = Collection.objects.create(owner=user, name="Leituras")
    item = send(api, "a.pdf", pdf(), collection=str(collection.id), visibility="shared").json()["items"][0]
    assert item["visibility"] == "shared"
    assert item["collections"] == [str(collection.id)]


def test_upload_into_malformed_collection_is_not_found(api, pdf, send):
    assert send(api, "a.pdf", pdf(), collection="nao-e-um-uuid").status_code == 404
    assert not Document.objects.exists()
