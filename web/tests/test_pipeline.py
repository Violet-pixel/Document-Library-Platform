import json
import time
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import redis as r
from apps.library.models import Document
from apps.processing import queue, stages
from apps.processing.models import Job
from apps.processing.worker import Worker, recover_stale

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def queued(api, pdf, send):
    def factory(name="relatorio.pdf", content=None):
        item = send(api, name, content or pdf()).json()["items"][0]
        return Document.objects.get(pk=item["id"])

    return factory


def test_extract_then_describe(queued, fake_processor):
    document = queued()
    fake = fake_processor()
    assert stages.handle("extract", document.id, "w1", transport=fake.transport).status == "done"
    assert fake.calls[0] == {
        "source": f"documents/{document.id}/original.pdf",
        "kind": "pdf",
        "output_dir": f"documents/{document.id}",
        "cover_width": 480,
    }
    document.refresh_from_db()
    assert document.status == "describing"
    assert document.title == "Guia de Arquitetura de Software" and document.author == "Equipe Exemplo"
    assert document.page_count == 3 and document.cover_color == "#c7b89c"
    assert document.metadata["producer"] == "ReportLab"
    assert r.client().xlen(queue.DESCRIBE) == 1

    assert stages.handle("describe", document.id, "w1").status == "done"
    document.refresh_from_db()
    assert document.status == "ready" and document.processed_at
    assert 40 < len(document.summary) <= 360
    assert document.language == "pt"
    assert document.search_vector
    assert [j.status for j in Job.objects.order_by("started_at")] == ["succeeded", "succeeded"]


def test_duplicate_message_is_ignored(queued, fake_processor):
    document = queued()
    fake = fake_processor()
    stages.handle("extract", document.id, "w1", transport=fake.transport)
    assert stages.handle("extract", document.id, "w2", transport=fake.transport).status == "skipped"
    assert len(fake.calls) == 1


def test_rejected_document_fails_without_retry(queued, fake_processor):
    document = queued()
    fake = fake_processor(status=422, body={"error": "encrypted", "message": "PDF protegido por senha."})
    outcome = stages.handle("extract", document.id, "w1", transport=fake.transport)
    document.refresh_from_db()
    assert outcome.status == "failed" and document.status == "failed"
    assert document.status_detail == "PDF protegido por senha."
    assert r.client().zcard(queue.DELAYED) == 0


def test_transient_error_retries_with_backoff_then_fails(queued, fake_processor, settings):
    settings.PIPELINE = {**settings.PIPELINE, "max_attempts": 2}
    document = queued()
    fake = fake_processor(status=503, body={"error": "busy", "message": "sem vaga"})
    assert stages.handle("extract", document.id, "w1", transport=fake.transport).status == "retry"
    document.refresh_from_db()
    assert document.status == "queued" and "Nova tentativa" in document.status_detail
    assert r.client().zcard(queue.DELAYED) == 1
    assert stages.handle("extract", document.id, "w1", transport=fake.transport).status == "failed"
    statuses = list(Job.objects.order_by("started_at").values_list("status", flat=True))
    assert statuses == ["retrying", "failed"]


def test_delayed_items_are_released_when_due(queued):
    document = queued()
    conn = r.client()
    conn.delete(queue.EXTRACT)
    queue.enqueue_later("extract", document.id, 60)
    assert queue.release_due(conn) == 0
    assert queue.release_due(conn, now=time.time() + 61) == 1
    assert conn.xlen(queue.EXTRACT) == 1 and conn.zcard(queue.DELAYED) == 0


def test_backoff_grows_and_has_cap():
    assert [queue.backoff(n) for n in (1, 2, 3)] == [5, 15, 45]
    assert queue.backoff(10) == 300


def test_docx_html_is_sanitized(queued, docx_file, fake_processor):
    document = queued("manual.docx", docx_file())
    html = (
        '<h1 id="s-1" data-b="0">Boas-vindas</h1><p data-b="1" onclick="x()">Olá <script>alert(1)</script>'
        '<a href="javascript:alert(1)">link</a> <a href="https://exemplo.dev">site</a></p>'
        '<img src="media/image1.png" alt="Logo" data-b="2">'
    )
    stages.handle("extract", document.id, "w1", transport=fake_processor(html=html).transport)
    document.refresh_from_db()
    safe = document.reader_path.read_text()
    assert document.has_reader_html and document.cover_generated
    assert "<script" not in safe and "onclick" not in safe and "javascript:" not in safe
    assert 'id="s-1"' in safe and 'data-b="1"' in safe
    assert f'src="/api/v1/documents/{document.id}/media/image1.png"' in safe
    assert 'rel="noopener noreferrer"' in safe


def test_bad_metadata_title_is_ignored(queued, fake_processor):
    document = queued("relatorio_final.pdf")
    stages.handle("extract", document.id, "w1", transport=fake_processor(body={"title": "Microsoft Word - rel.docx"}).transport)
    document.refresh_from_db()
    assert document.title == "Relatorio final"


@pytest.mark.parametrize(
    "title", ["Untitled", "Untitled document", "Documento sem título", "Sem título 1", "Document1", "Documento 2"]
)
def test_placeholder_titles_are_ignored(title):
    assert stages.good_metadata(title, 300) == ""


def test_real_titles_are_kept():
    assert stages.good_metadata("Documentos do RH", 300) == "Documentos do RH"
    assert stages.good_metadata("Untitled documentary", 300) == "Untitled documentary"


def test_recover_stale_documents(queued):
    document = queued()
    conn = r.client()
    conn.delete(queue.EXTRACT)
    old = timezone.now() - timedelta(hours=2)
    Document.objects.filter(pk=document.pk).update(status="extracting", updated_at=old)
    assert recover_stale() == 1
    document.refresh_from_db()
    assert document.status == "queued" and conn.xlen(queue.EXTRACT) == 1


def test_worker_consumes_stream(queued, fake_processor, monkeypatch):
    document = queued()
    fake = fake_processor()
    original = stages.handle
    monkeypatch.setattr(stages, "handle", lambda stage, doc_id, worker: original(stage, doc_id, worker, transport=fake.transport))
    worker = Worker(["extract", "describe"], threads=1)
    queue.ensure_groups()
    conn = r.client()
    for _ in range(2):
        batch = conn.xreadgroup(queue.GROUP, "t", {queue.EXTRACT: ">", queue.DESCRIBE: ">"}, count=1, block=100)
        for stream, messages in batch:
            for message_id, fields in messages:
                worker.execute({queue.EXTRACT: "extract", queue.DESCRIBE: "describe"}[stream], fields["document_id"], "t")
                conn.xack(stream, queue.GROUP, message_id)
    document.refresh_from_db()
    assert document.status == "ready" and worker.processed == 2
    worker.heartbeat()
    data = conn.hgetall(f"workers:{worker.name}")
    assert data["processed"] == "2" and conn.ttl(f"workers:{worker.name}") > 0


def test_queue_stats(queued):
    queued()
    queue.ensure_groups()
    stats = queue.stats()
    assert stats["extract"]["length"] == 1 and stats["delayed"] == 0


def test_events_are_published(queued, fake_processor):
    conn = r.client()
    pubsub = conn.pubsub()
    document = queued()
    pubsub.subscribe(f"events:user:{document.owner_id}")
    pubsub.get_message(timeout=1)
    stages.handle("extract", document.id, "w1", transport=fake_processor().transport)
    received = []
    for _ in range(5):
        message = pubsub.get_message(timeout=1)
        if message and message["type"] == "message":
            received.append(json.loads(message["data"]))
    assert {"extracting", "describing"} <= {m["status"] for m in received}
    pubsub.close()


def test_worker_recovers_when_redis_is_wiped(queued, fake_processor, monkeypatch):
    document = queued()
    conn = r.client()
    conn.flushdb()  # Redis reiniciado sem persistência: some a fila e o grupo
    worker = Worker(["extract"], threads=1)
    calls = []
    monkeypatch.setattr(worker, "execute", lambda stage, doc_id, consumer: (calls.append(doc_id), worker.stop.set()))
    old = timezone.now() - timedelta(hours=2)
    Document.objects.filter(pk=document.pk).update(updated_at=old)
    worker.maintenance()  # recria os grupos e devolve o documento parado para a fila
    worker.consume(0)
    assert calls == [str(document.id)]
