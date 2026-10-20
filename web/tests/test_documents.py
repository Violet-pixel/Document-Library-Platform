import pytest

from apps.library.models import Collection, Document
from apps.processing import stages

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def ready(api, pdf, send, fake_processor):
    """Envia e processa um PDF com o processador simulado."""

    def factory(client=None, name="guia.pdf", **kwargs):
        content = pdf(title=name)
        item = send(client or api, name, content, **kwargs).json()["items"][0]
        fake = fake_processor(body={"title": name.replace(".pdf", "").title()})
        stages.handle("extract", item["id"], "teste", transport=fake.transport)
        stages.handle("describe", item["id"], "teste")
        return Document.objects.get(pk=item["id"])

    return factory


def test_processed_document_appears_with_cover_and_summary(api, ready):
    document = ready()
    data = api.get(f"/api/v1/documents/{document.id}").json()
    assert data["status"] == "ready"
    assert data["cover_url"].endswith("?v=1")
    assert data["summary"] and data["summary_source"] == "local"
    assert data["outline"][0]["title"] == "Capítulo 1"
    assert {t["source"] for t in data["tags"]} == {"ia"}
    assert api.get(data["cover_url"]).status_code == 200


def test_private_documents_are_invisible_to_others(api_for, other, ready):
    document = ready()
    client = api_for(other)
    assert client.get(f"/api/v1/documents/{document.id}").status_code == 404
    assert client.get(f"/api/v1/documents/{document.id}/file").status_code == 404
    assert client.get("/api/v1/documents?scope=all").json()["count"] == 0


def test_shared_documents_are_readable_but_not_editable(api, api_for, other, ready):
    document = ready(visibility="shared")
    client = api_for(other)
    assert client.get("/api/v1/documents?scope=shared").json()["count"] == 1
    assert client.get("/api/v1/documents").json()["count"] == 0
    assert client.get(f"/api/v1/documents/{document.id}").json()["is_owner"] is False
    assert client.patch(f"/api/v1/documents/{document.id}", {"title": "x"}, format="json").status_code == 403
    assert client.delete(f"/api/v1/documents/{document.id}").status_code == 403
    assert client.put(f"/api/v1/documents/{document.id}/reading", {"page": 2}, format="json").status_code == 200


def test_edit_title_locks_metadata(api, ready, fake_processor):
    document = ready()
    api.patch(f"/api/v1/documents/{document.id}", {"title": "Meu título", "author": "Eu"}, format="json")
    document.refresh_from_db()
    assert document.metadata_locked
    api.post(f"/api/v1/documents/{document.id}/reprocess")
    stages.handle("extract", document.id, "teste", transport=fake_processor().transport)
    document.refresh_from_db()
    assert document.title == "Meu título" and document.cover_version == 2


def test_search_full_text_accent_insensitive(api, ready):
    ready(name="arquitetura.pdf")
    results = api.get("/api/v1/documents", {"q": "decisoes tecnicas"}).json()
    assert results["count"] == 1
    assert "<mark>" in results["results"][0]["snippet"]
    assert api.get("/api/v1/documents", {"q": "astronomia"}).json()["count"] == 0
    assert api.get("/api/v1/documents", {"q": "Arquitetur"}).json()["count"] == 1  # trigramas no título


def test_snippet_escapes_html(api, user, ready):
    document = ready()
    document.content.text = "Os registros de <b>decisão</b> <script>alert(1)</script> importantes"
    document.content.save()
    from apps.library.services import refresh_search

    refresh_search(document.id)
    snippet = api.get("/api/v1/documents", {"q": "registros"}).json()["results"][0]["snippet"]
    assert "<script>" not in snippet and "<b>" not in snippet
    assert snippet.startswith("<mark>registros</mark>")


def test_filters_and_sorting(api, ready):
    a = ready(name="alfa.pdf")
    b = ready(name="beta.pdf")
    api.put(f"/api/v1/documents/{a.id}/reading", {"shelf": "lendo", "favorite": True}, format="json")
    assert [d["id"] for d in api.get("/api/v1/documents?shelf=lendo").json()["results"]] == [str(a.id)]
    assert api.get("/api/v1/documents?favorite=1").json()["count"] == 1
    titles = [d["title"] for d in api.get("/api/v1/documents?sort=title").json()["results"]]
    assert titles == sorted(titles)
    assert api.get("/api/v1/documents?kind=docx").json()["count"] == 0
    assert api.get("/api/v1/documents?status=ready").json()["count"] == 2
    tag = b.document_tags.first().tag.slug
    assert api.get(f"/api/v1/documents?tag={tag}").json()["count"] >= 1


def test_reading_state_and_open(api, user, ready):
    document = ready()
    reading = api.post(f"/api/v1/documents/{document.id}/open").json()
    assert reading["shelf"] == "lendo" and reading["last_opened_at"]
    reading = api.put(f"/api/v1/documents/{document.id}/reading", {"page": 99, "progress": 1.7}, format="json").json()
    assert reading["page"] == 3 and reading["progress"] == 1.0
    reading = api.put(f"/api/v1/documents/{document.id}/reading", {"shelf": "lido"}, format="json").json()
    assert reading["finished_at"]
    stats = api.get("/api/v1/stats").json()
    assert stats["shelves"]["lido"] == 1 and stats["continue_reading"][0]["id"] == str(document.id)


def test_annotations(api, api_for, other, ready):
    document = ready(visibility="shared")
    url = f"/api/v1/documents/{document.id}/annotations"
    note = api.post(url, {"kind": "note", "page": 2, "note": "Rever este trecho"}, format="json")
    assert note.status_code == 201
    highlight = {"kind": "highlight", "page": 1, "quote": "camadas", "anchor": {"rects": [[0.1, 0.2, 0.3, 0.02]]}}
    assert api.post(url, highlight, format="json").status_code == 201
    assert api.post(url, {"kind": "note", "page": 1, "note": "  "}, format="json").status_code == 400
    assert api.post(url, {**highlight, "color": "neon"}, format="json").status_code == 400
    assert len(api.get(url).json()) == 2
    assert api_for(other).get(url).json() == []  # anotações são pessoais
    note_id = note.json()["id"]
    assert api_for(other).delete(f"/api/v1/annotations/{note_id}").status_code == 404
    assert api.patch(f"/api/v1/annotations/{note_id}", {"note": "Feito"}, format="json").json()["note"] == "Feito"
    assert api.delete(f"/api/v1/annotations/{note_id}").status_code == 204


def test_collections(api, user, ready):
    a, b = ready(name="a.pdf"), ready(name="b.pdf")
    created = api.post("/api/v1/collections", {"name": "Estudos"}, format="json").json()
    assert api.post("/api/v1/collections", {"name": "estudos"}, format="json").status_code == 400
    url = f"/api/v1/collections/{created['id']}"
    assert api.post(f"{url}/documents", {"document_ids": [str(a.id), str(b.id)]}, format="json").json()["added"] == 2
    api.put(f"{url}/order", {"document_ids": [str(b.id), str(a.id)]}, format="json")
    ordered = api.get(f"/api/v1/documents?collection={created['id']}&sort=collection").json()["results"]
    assert [d["id"] for d in ordered] == [str(b.id), str(a.id)]
    listing = api.get("/api/v1/collections").json()
    assert listing[0]["document_count"] == 2 and len(listing[0]["covers"]) == 2
    assert api.delete(f"{url}/documents/{a.id}").status_code == 204
    assert api.delete(url).status_code == 204
    assert Collection.objects.count() == 0 and Document.objects.count() == 2


def test_tags_by_user_keep_on_redescribe(api, ready):
    document = ready()
    api.put(f"/api/v1/documents/{document.id}/tags", {"tags": ["Leitura obrigatória", "equipe"]}, format="json")
    api.post(f"/api/v1/documents/{document.id}/describe")
    stages.handle("describe", document.id, "teste")
    tags = {t["name"]: t["source"] for t in api.get(f"/api/v1/documents/{document.id}").json()["tags"]}
    assert tags["leitura obrigatória"] == "usuario" and tags["equipe"] == "usuario"
    assert "ia" in tags.values()


def test_file_supports_range_requests(api, ready):
    document = ready()
    full = api.get(f"/api/v1/documents/{document.id}/file")
    assert full.status_code == 200 and full["Accept-Ranges"] == "bytes"
    part = api.get(f"/api/v1/documents/{document.id}/file", HTTP_RANGE="bytes=0-99")
    assert part.status_code == 206 and len(part.content) == 100
    assert part["Content-Range"].startswith("bytes 0-99/")
    download = api.get(f"/api/v1/documents/{document.id}/file?download=1")
    assert download["Content-Disposition"].startswith("attachment")
    assert api.get(f"/api/v1/documents/{document.id}/file", HTTP_IF_NONE_MATCH=full["ETag"]).status_code == 304


def test_delete_removes_files(api, ready):
    document = ready()
    folder = document.folder
    assert folder.exists()
    assert api.delete(f"/api/v1/documents/{document.id}").status_code == 204
    assert not folder.exists() and not Document.objects.exists()


def test_reader_html_only_for_docx(api, ready):
    document = ready()
    assert api.get(f"/api/v1/documents/{document.id}/reader").status_code == 404
    assert api.get(f"/api/v1/documents/{document.id}/media/..%2Fsecret").status_code == 404


def test_stats(api, ready, user):
    document = ready()
    api.put(f"/api/v1/documents/{document.id}/reading", {"favorite": True}, format="json")
    stats = api.get("/api/v1/stats").json()
    assert stats["total"] == 1 and stats["pdf"] == 1 and stats["favorites"] == 1


def test_pages_require_login(client, user):
    assert client.get("/").status_code == 302
    client.force_login(user)
    response = client.get("/biblioteca")
    assert response.status_code == 200 and b"boot" in response.content
    assert "Content-Security-Policy" in response.headers
