"""Regras da biblioteca: envio de arquivos, deduplicação, etiquetas, busca e exclusão."""

import hashlib
import logging
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core import events
from apps.library.models import Collection, CollectionItem, Document, DocumentTag, Tag
from apps.processing import queue

log = logging.getLogger(__name__)

EXTENSIONS = {".pdf": Document.Kind.PDF, ".docx": Document.Kind.DOCX}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class UploadRejected(Exception):
    pass


@dataclass
class UploadResult:
    document: Document
    duplicate: bool


def detect_kind(path: Path, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    with open(path, "rb") as handle:
        head = handle.read(1024)
    if ext == ".doc" or head.startswith(OLE_MAGIC):
        raise UploadRejected("Arquivos .doc antigos não são suportados. Abra no Word e salve como .docx.")
    if b"%PDF-" in head:
        return Document.Kind.PDF
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            raise UploadRejected("O arquivo .docx está corrompido.") from None
        if "word/document.xml" in names:
            return Document.Kind.DOCX
        raise UploadRejected("Este arquivo compactado não é um documento do Word (.docx).")
    if ext in EXTENSIONS:
        raise UploadRejected(f"O conteúdo não corresponde a um arquivo {ext}. Ele pode estar corrompido.")
    raise UploadRejected("Formato não suportado. Envie arquivos PDF ou DOCX.")


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_]+|(?<=\w)-(?=\w)|\.+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if not stem:
        return "Documento sem título"
    return stem[0].upper() + stem[1:] if stem.islower() else stem


def _write_temp(uploaded) -> tuple[Path, str, int]:
    tmp_dir = settings.DATA_ROOT / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4()}.part"
    digest = hashlib.sha256()
    size = 0
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    try:
        with open(tmp_path, "wb") as out:
            for chunk in uploaded.chunks(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise UploadRejected(f"O arquivo passa do limite de {settings.MAX_UPLOAD_MB} MB.")
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    if size == 0:
        tmp_path.unlink(missing_ok=True)
        raise UploadRejected("O arquivo está vazio.")
    return tmp_path, digest.hexdigest(), size


def store_upload(owner, uploaded, visibility: str = Document.Visibility.PRIVATE, collection=None) -> UploadResult:
    filename = Path(uploaded.name or "documento").name[:255]
    tmp_path, sha256, size = _write_temp(uploaded)
    try:
        kind = detect_kind(tmp_path, filename)
        existing = Document.objects.filter(owner=owner, sha256=sha256).first()
        if existing:
            tmp_path.unlink(missing_ok=True)
            if collection:
                add_to_collection(collection, [existing])
            return UploadResult(existing, True)

        with transaction.atomic():
            document = Document.objects.create(
                owner=owner,
                title=title_from_filename(filename),
                kind=kind,
                original_name=filename,
                size_bytes=size,
                sha256=sha256,
                visibility=visibility,
            )
            document.folder.mkdir(parents=True, exist_ok=True)
            os.replace(tmp_path, document.file_path)
            if collection:
                add_to_collection(collection, [document])
            transaction.on_commit(lambda: _after_create(document))
        return UploadResult(document, False)
    finally:
        tmp_path.unlink(missing_ok=True)


def _after_create(document: Document) -> None:
    queue.enqueue("extract", document.id)
    events.document_event(document, "document.created")


def requeue(document: Document, stage: str = "extract") -> None:
    status = Document.Status.QUEUED if stage == "extract" else Document.Status.DESCRIBING
    Document.objects.filter(pk=document.pk).update(status=status, status_detail="", attempts=0)
    document.status = status
    transaction.on_commit(lambda: (queue.enqueue(stage, document.id), events.document_event(document)))


def delete_document_files(document: Document) -> None:
    folder = document.folder
    if folder.is_dir() and folder.resolve().is_relative_to(settings.DATA_ROOT.resolve()):
        shutil.rmtree(folder, ignore_errors=True)


def delete_document(document: Document) -> None:
    owner_id, shared, doc_id = document.owner_id, document.visibility == "shared", str(document.id)
    delete_document_files(document)
    document.delete()
    events.publish(owner_id, "document.deleted", shared=shared, id=doc_id)


def normalize_tag(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name)).strip().lower()
    return name[:40]


def set_tags(document: Document, names: list[str], source: str = DocumentTag.Source.USER) -> None:
    """Substitui as etiquetas de uma origem, mantendo as da outra (a IA não apaga o que o usuário escolheu)."""
    clean = []
    for name in names:
        name = normalize_tag(name)
        slug = slugify(name)[:48]
        if name and slug and slug not in {c[1] for c in clean}:
            clean.append((name, slug))
    clean = clean[:12]
    with transaction.atomic():
        if source == DocumentTag.Source.USER:
            DocumentTag.objects.filter(document=document).delete()
        else:
            DocumentTag.objects.filter(document=document, source=source).delete()
        existing = set(DocumentTag.objects.filter(document=document).values_list("tag__slug", flat=True))
        for name, slug in clean:
            if slug in existing:
                continue
            tag, _ = Tag.objects.get_or_create(owner=document.owner, slug=slug, defaults={"name": name})
            DocumentTag.objects.create(document=document, tag=tag, source=source)
        Tag.objects.filter(owner=document.owner, document_tags__isnull=True).delete()


def add_to_collection(collection: Collection, documents) -> int:
    last = collection.items.order_by("-position").values_list("position", flat=True).first() or 0
    added = 0
    for document in documents:
        _, created = CollectionItem.objects.get_or_create(
            collection=collection, document=document, defaults={"position": last + added + 1}
        )
        added += int(created)
    if added:
        Collection.objects.filter(pk=collection.pk).update(updated_at=timezone.now())
    return added


SEARCH_SQL = """
UPDATE library_document d SET search_vector =
    setweight(to_tsvector('pt_unaccent', coalesce(d.title, '')), 'A') ||
    setweight(to_tsvector('pt_unaccent', coalesce(d.author, '')), 'B') ||
    setweight(to_tsvector('pt_unaccent', coalesce(d.summary, '') || ' ' || coalesce(d.description, '') || ' ' ||
        coalesce((SELECT string_agg(t.name, ' ') FROM library_documenttag dt
                  JOIN library_tag t ON t.id = dt.tag_id WHERE dt.document_id = d.id), '')), 'B') ||
    setweight(to_tsvector('pt_unaccent', coalesce(
        (SELECT left(c.text, %s) FROM library_documentcontent c WHERE c.document_id = d.id), '')), 'C')
WHERE d.id = %s
"""

SEARCH_TEXT_LIMIT = 300_000


def refresh_search(document_id) -> None:
    with connection.cursor() as cursor:
        cursor.execute(SEARCH_SQL, [SEARCH_TEXT_LIMIT, str(document_id)])
