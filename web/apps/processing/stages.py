"""Etapas do processamento de um documento: leitura do arquivo (processador Java) e descrição por IA."""

import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai import service as ai
from apps.core import events
from apps.library import services
from apps.library.models import Document, DocumentContent, DocumentTag
from apps.processing import processor, queue, sanitize
from apps.processing.models import Job

log = logging.getLogger(__name__)

CLAIMABLE = {
    "extract": [Document.Status.QUEUED, Document.Status.EXTRACTING],
    "describe": [Document.Status.DESCRIBING],
}
RUNNING_STATUS = {"extract": Document.Status.EXTRACTING, "describe": Document.Status.DESCRIBING}
BAD_TITLES = re.compile(
    r"^(untitled( document)?( \d+)?|(documento )?sem t[ií]tulo( \d+)?|documento? ?\d*|microsoft word\s*-.*|.*\.(docx?|pdf|tmp))$",
    re.I,
)


@dataclass
class Outcome:
    status: str  # done | retry | failed | skipped
    detail: str = ""


def claim(document_id, stage: str) -> Document | None:
    """Marca o documento como em processamento nesta etapa. Mensagem repetida ou atrasada não faz nada."""
    with transaction.atomic():
        document = Document.objects.select_for_update(skip_locked=True).filter(pk=document_id).first()
        if not document or document.status not in CLAIMABLE[stage]:
            return None
        document.status = RUNNING_STATUS[stage]
        document.attempts += 1
        document.status_detail = ""
        document.save(update_fields=["status", "attempts", "status_detail", "updated_at"])
    events.document_event(document)
    return document


def good_metadata(value: str | None, limit: int) -> str:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    if len(value) < 3 or BAD_TITLES.match(value):
        return ""
    return value[:limit]


def apply_extraction(document: Document, result: dict) -> None:
    folder = document.folder
    html_info = result.get("html") or None
    has_html = False
    if html_info and html_info.get("file"):
        raw_path = (folder / html_info["file"]).resolve()
        if raw_path.is_relative_to(folder.resolve()) and raw_path.is_file():
            safe = sanitize.reader_html(raw_path.read_text(encoding="utf-8"), document.id)
            document.reader_path.write_text(safe, encoding="utf-8")
            has_html = True

    cover = result.get("cover") or {}
    metadata = {
        key: result.get(key)
        for key in ("subject", "keywords", "created_at", "modified_at", "producer", "creator", "page_width",
                    "page_height", "encrypted", "warnings", "elapsed_ms", "char_count", "text_truncated")
        if result.get(key) not in (None, "", [])
    }

    with transaction.atomic():
        document.refresh_from_db()
        document.page_count = result.get("page_count") or None
        document.word_count = result.get("word_count") or 0
        document.language = (result.get("language") or "")[:16]
        document.outline = (result.get("outline") or [])[:500]
        document.metadata = metadata
        document.has_reader_html = has_html
        if cover.get("file"):
            document.cover_width = cover.get("width")
            document.cover_height = cover.get("height")
            document.cover_color = (cover.get("color") or "")[:7]
            document.cover_generated = bool(cover.get("generated"))
            document.cover_version += 1
        if not document.metadata_locked:
            title = good_metadata(result.get("title"), 300)
            author = good_metadata(result.get("author"), 200)
            if title:
                document.title = title
            if author:
                document.author = author
        document.status = Document.Status.DESCRIBING
        document.attempts = 0
        document.status_detail = ""
        document.save()
        DocumentContent.objects.update_or_create(
            document=document,
            defaults={"text": result.get("text") or "", "text_truncated": bool(result.get("text_truncated"))},
        )
        services.refresh_search(document.id)
        transaction.on_commit(lambda: queue.enqueue("describe", document.id))


def run_extract(document: Document, worker: str, transport=None) -> Outcome:
    job = Job.objects.create(document=document, stage=Job.Stage.EXTRACT, attempt=document.attempts, worker=worker)
    try:
        result = processor.process(document, transport=transport)
        apply_extraction(document, result)
    except processor.DocumentRejected as exc:
        job.finish(Job.Status.FAILED, str(exc))
        return fail(document, str(exc))
    except Exception as exc:  # passageiro: processador fora do ar, rede, bug pontual
        log.warning("Extração de %s falhou (tentativa %s): %s", document.id, document.attempts, exc)
        if document.attempts >= settings.PIPELINE["max_attempts"]:
            job.finish(Job.Status.FAILED, str(exc))
            return fail(document, "Não foi possível ler o arquivo depois de várias tentativas. Tente de novo mais tarde.")
        delay = queue.backoff(document.attempts)
        job.finish(Job.Status.RETRYING, str(exc), retry_in_s=delay)
        Document.objects.filter(pk=document.pk).update(
            status=Document.Status.QUEUED, status_detail=f"Nova tentativa em {int(delay)} s"
        )
        queue.enqueue_later("extract", document.id, delay)
        document.status = Document.Status.QUEUED
        events.document_event(document)
        return Outcome("retry", str(exc))
    job.finish(
        Job.Status.SUCCEEDED,
        pages=result.get("page_count"),
        words=result.get("word_count"),
        processor_ms=result.get("elapsed_ms"),
    )
    document.status = Document.Status.DESCRIBING
    events.document_event(document)
    return Outcome("done")


def run_describe(document: Document, worker: str, transport=None) -> Outcome:
    job = Job.objects.create(document=document, stage=Job.Stage.DESCRIBE, attempt=document.attempts, worker=worker)
    content = DocumentContent.objects.filter(document=document).first()
    text = content.text if content else ""
    try:
        result = ai.describe(document, text, transport=transport)
    except Exception as exc:
        log.exception("Descrição de %s falhou", document.id)
        result = ai.Description("", [], "local", warnings=[f"Falha inesperada: {exc}"])
    with transaction.atomic():
        document.refresh_from_db()
        document.summary = result.summary
        document.summary_source = result.source
        document.summary_model = result.model
        document.summary_at = timezone.now()
        if result.language and not document.language:
            document.language = result.language
        document.status = Document.Status.READY
        document.status_detail = ""
        document.attempts = 0
        document.processed_at = document.processed_at or timezone.now()
        document.save()
        if result.tags:
            services.set_tags(document, result.tags, DocumentTag.Source.AI)
        services.refresh_search(document.id)
    job.finish(
        Job.Status.SUCCEEDED,
        "; ".join(result.warnings),
        provider=result.source,
        model=result.model,
        fallback=bool(result.warnings),
    )
    events.document_event(document)
    return Outcome("done")


def fail(document: Document, message: str) -> Outcome:
    Document.objects.filter(pk=document.pk).update(status=Document.Status.FAILED, status_detail=message[:1000])
    document.status = Document.Status.FAILED
    events.document_event(document)
    return Outcome("failed", message)


RUNNERS = {"extract": run_extract, "describe": run_describe}


def handle(stage: str, document_id, worker: str, transport=None) -> Outcome:
    document = claim(document_id, stage)
    if document is None:
        return Outcome("skipped")
    return RUNNERS[stage](document, worker, transport=transport)
