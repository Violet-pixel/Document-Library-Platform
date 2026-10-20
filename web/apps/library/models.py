import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Document(models.Model):
    class Kind(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "DOCX"

    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        EXTRACTING = "extracting", "Lendo o documento"
        DESCRIBING = "describing", "Escrevendo a descrição"
        READY = "ready", "Pronto"
        FAILED = "failed", "Falhou"

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Só eu"
        SHARED = "shared", "Todos da instalação"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")

    title = models.CharField("título", max_length=300)
    author = models.CharField("autor", max_length=200, blank=True)
    description = models.TextField("descrição do usuário", blank=True)
    metadata_locked = models.BooleanField(
        "título e autor editados à mão", default=False, help_text="Impede que os metadados do arquivo sobrescrevam."
    )

    summary = models.TextField("descrição por IA", blank=True)
    summary_source = models.CharField("origem da descrição", max_length=20, blank=True)
    summary_model = models.CharField("modelo", max_length=100, blank=True)
    summary_at = models.DateTimeField(null=True, blank=True)

    kind = models.CharField("tipo", max_length=8, choices=Kind.choices)
    original_name = models.CharField("nome do arquivo", max_length=255)
    size_bytes = models.BigIntegerField("tamanho")
    sha256 = models.CharField(max_length=64)
    page_count = models.PositiveIntegerField("páginas", null=True, blank=True)
    word_count = models.PositiveIntegerField("palavras", null=True, blank=True)
    language = models.CharField("idioma", max_length=16, blank=True)

    cover_width = models.PositiveIntegerField(null=True, blank=True)
    cover_height = models.PositiveIntegerField(null=True, blank=True)
    cover_color = models.CharField(max_length=7, blank=True)
    cover_generated = models.BooleanField(default=False)
    cover_version = models.PositiveIntegerField(default=0)
    has_reader_html = models.BooleanField(default=False)

    outline = models.JSONField("sumário", default=list, blank=True)
    metadata = models.JSONField("metadados do arquivo", default=dict, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    status_detail = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    search_vector = SearchVectorField(null=True, editable=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "library_document"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "sha256"], name="library_document_owner_sha256_unique"),
        ]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="library_doc_owner_created"),
            models.Index(
                fields=["visibility", "-created_at"],
                name="library_doc_shared",
                condition=models.Q(visibility="shared"),
            ),
            GinIndex(fields=["search_vector"], name="library_doc_search"),
            GinIndex(fields=["title"], name="library_doc_title_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self):
        return self.title

    @property
    def folder(self) -> Path:
        return settings.DATA_ROOT / self.relative_folder

    @property
    def relative_folder(self) -> str:
        return f"documents/{self.id}"

    @property
    def file_path(self) -> Path:
        return self.folder / f"original.{self.kind}"

    @property
    def cover_path(self) -> Path:
        return self.folder / "cover.jpg"

    @property
    def reader_path(self) -> Path:
        return self.folder / "reader.safe.html"

    @property
    def mime_type(self) -> str:
        if self.kind == self.Kind.PDF:
            return "application/pdf"
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    @property
    def has_cover(self) -> bool:
        return self.cover_version > 0


class DocumentContent(models.Model):
    """Texto extraído, separado da tabela principal para manter as listagens leves."""

    document = models.OneToOneField(Document, on_delete=models.CASCADE, primary_key=True, related_name="content")
    text = models.TextField(blank=True)
    text_truncated = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "library_documentcontent"


class Tag(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=40)
    slug = models.SlugField(max_length=48)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "library_tag"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["owner", "slug"], name="library_tag_owner_slug_unique")]

    def __str__(self):
        return self.name


class DocumentTag(models.Model):
    class Source(models.TextChoices):
        AI = "ia", "IA"
        USER = "usuario", "Usuário"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="document_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="document_tags")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.USER)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "library_documenttag"
        constraints = [models.UniqueConstraint(fields=["document", "tag"], name="library_documenttag_unique")]


class Collection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collections")
    name = models.CharField("nome", max_length=80)
    description = models.CharField("descrição", max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    documents = models.ManyToManyField(Document, through="CollectionItem", related_name="collections")

    class Meta:
        db_table = "library_collection"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint("owner", Lower("name"), name="library_collection_owner_name_unique"),
        ]

    def __str__(self):
        return self.name


class CollectionItem(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="items")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="collection_items")
    position = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "library_collectionitem"
        ordering = ["position", "added_at"]
        constraints = [
            models.UniqueConstraint(fields=["collection", "document"], name="library_collectionitem_unique"),
        ]


class ReadingState(models.Model):
    class Shelf(models.TextChoices):
        TO_READ = "para_ler", "Quero ler"
        READING = "lendo", "Lendo"
        DONE = "lido", "Lidos"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_states")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="reading_states")
    shelf = models.CharField(max_length=10, choices=Shelf.choices, blank=True)
    page = models.PositiveIntegerField(default=1)
    progress = models.FloatField(default=0)
    location = models.JSONField(default=dict, blank=True)
    favorite = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "library_readingstate"
        constraints = [
            models.UniqueConstraint(fields=["user", "document"], name="library_readingstate_unique"),
            models.CheckConstraint(
                condition=models.Q(progress__gte=0) & models.Q(progress__lte=1), name="library_readingstate_progress"
            ),
        ]
        indexes = [models.Index(fields=["user", "-last_opened_at"], name="library_reading_recent")]


class Annotation(models.Model):
    class Kind(models.TextChoices):
        NOTE = "note", "Nota"
        HIGHLIGHT = "highlight", "Destaque"
        BOOKMARK = "bookmark", "Marcador"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="annotations")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="annotations")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    page = models.PositiveIntegerField(null=True, blank=True)
    anchor = models.JSONField(default=dict, blank=True)
    quote = models.TextField(blank=True)
    note = models.TextField(blank=True)
    color = models.CharField(max_length=16, default="salvia")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "library_annotation"
        ordering = ["page", "created_at"]
        indexes = [models.Index(fields=["user", "document"], name="library_annotation_user_doc")]
