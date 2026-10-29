import re
import uuid
from html import escape

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db import connection, transaction
from django.db.models import Count, F, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Lower
from django.http import Http404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import events
from apps.core.api import ApiError, Pagination
from apps.core.files import file_response
from apps.library import services
from apps.library.models import (
    Annotation,
    Collection,
    CollectionItem,
    Document,
    DocumentTag,
    ReadingState,
    Tag,
)
from apps.library.serializers import (
    AnnotationSerializer,
    CollectionDocumentsSerializer,
    CollectionSerializer,
    DocumentDetailSerializer,
    DocumentSerializer,
    ReadingSerializer,
    TagsInputSerializer,
    UploadSerializer,
)

PROCESSING = [Document.Status.QUEUED, Document.Status.EXTRACTING, Document.Status.DESCRIBING]
MEDIA_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
UUID_PATH = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def visible_documents(user):
    return Document.objects.filter(Q(owner=user) | Q(visibility=Document.Visibility.SHARED))


def with_relations(qs, user):
    return qs.select_related("owner").prefetch_related(
        Prefetch(
            "document_tags",
            queryset=DocumentTag.objects.select_related("tag").order_by("tag__name"),
            to_attr="prefetched_tags",
        ),
        Prefetch("reading_states", queryset=ReadingState.objects.filter(user=user), to_attr="my_reading"),
        Prefetch(
            "collection_items",
            queryset=CollectionItem.objects.filter(collection__owner=user),
            to_attr="prefetched_items",
        ),
    )


def snippets(ids, query: str) -> dict:
    if not ids or not query:
        return {}
    sql = """
        SELECT c.document_id, ts_headline('pt_unaccent', left(c.text, 100000),
               websearch_to_tsquery('pt_unaccent', %s),
               'MaxFragments=1, MaxWords=26, MinWords=12, StartSel=@@@[, StopSel=]@@@, FragmentDelimiter= … ')
        FROM library_documentcontent c WHERE c.document_id = ANY(%s::uuid[])
    """
    result = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, [query, [str(i) for i in ids]])
        for doc_id, text in cursor.fetchall():
            if text and "@@@[" in text:
                safe = escape(re.sub(r"\s+", " ", text).strip())
                result[str(doc_id)] = safe.replace("@@@[", "<mark>").replace("]@@@", "</mark>")
    return result


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    pagination_class = Pagination
    http_method_names = ["get", "post", "patch", "put", "delete", "head"]

    def get_serializer_class(self):
        return DocumentDetailSerializer if self.action == "retrieve" else DocumentSerializer

    def get_queryset(self):
        user = self.request.user
        return with_relations(visible_documents(user), user)

    def get_object(self):
        document = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])
        return document

    def owned_object(self) -> Document:
        document = self.get_object()
        if document.owner_id != self.request.user.id and not self.request.user.is_admin:
            raise ApiError("Só o dono do documento pode fazer isso.", "permission_denied", 403)
        return document

    def filter_list(self, qs):
        p = self.request.query_params
        user = self.request.user
        scope = p.get("scope", "mine")
        if scope == "mine":
            qs = qs.filter(owner=user)
        elif scope == "shared":
            qs = qs.filter(visibility=Document.Visibility.SHARED).exclude(owner=user)
        if p.get("kind") in Document.Kind.values:
            qs = qs.filter(kind=p["kind"])
        state = p.get("status")
        if state == "processing":
            qs = qs.filter(status__in=PROCESSING)
        elif state in {Document.Status.READY, Document.Status.FAILED}:
            qs = qs.filter(status=state)
        if p.get("shelf") in ReadingState.Shelf.values:
            qs = qs.filter(reading_states__user=user, reading_states__shelf=p["shelf"])
        if p.get("favorite") in {"1", "true"}:
            qs = qs.filter(reading_states__user=user, reading_states__favorite=True)
        if p.get("collection"):
            try:
                collection_id = uuid.UUID(p["collection"])
            except ValueError:
                raise ApiError("Coleção inválida.") from None
            qs = qs.filter(collection_items__collection_id=collection_id, collection_items__collection__owner=user)
        if p.get("tag"):
            qs = qs.filter(document_tags__tag__slug=p["tag"])
        return qs

    def sort_list(self, qs, query: str):
        sort = self.request.query_params.get("sort", "relevance" if query else "recent")
        last_opened = ReadingState.objects.filter(user=self.request.user, document=OuterRef("pk")).values(
            "last_opened_at"
        )[:1]
        if sort == "relevance" and query:
            return qs.order_by("-rank", "-similarity", "-created_at")
        if sort == "title":
            return qs.order_by(Lower("title"), "-created_at")
        if sort == "author":
            return qs.order_by(Lower("author").asc(nulls_last=True), Lower("title"))
        if sort == "last_read":
            return qs.annotate(opened=Subquery(last_opened)).order_by(F("opened").desc(nulls_last=True), "-created_at")
        if sort == "pages":
            return qs.order_by(F("page_count").desc(nulls_last=True), "-created_at")
        if sort == "size":
            return qs.order_by("-size_bytes")
        if sort == "collection" and self.request.query_params.get("collection"):
            return qs.order_by("collection_items__position", "-created_at")
        return qs.order_by("-created_at")

    @extend_schema(
        tags=["Documentos"],
        parameters=[
            OpenApiParameter("q", str, description="Busca em título, autor, descrição, etiquetas e texto completo."),
            OpenApiParameter("scope", str, enum=["mine", "shared", "all"], description="Padrão: mine."),
            OpenApiParameter("kind", str, enum=["pdf", "docx"]),
            OpenApiParameter("status", str, enum=["processing", "ready", "failed"]),
            OpenApiParameter("shelf", str, enum=["para_ler", "lendo", "lido"]),
            OpenApiParameter("favorite", bool),
            OpenApiParameter("collection", OpenApiTypes.UUID),
            OpenApiParameter("tag", str),
            OpenApiParameter(
                "sort", str, enum=["relevance", "recent", "title", "author", "last_read", "pages", "size", "collection"]
            ),
            OpenApiParameter("page", int),
            OpenApiParameter("page_size", int),
        ],
    )
    def list(self, request, *args, **kwargs):
        query = request.query_params.get("q", "").strip()[:200]
        qs = self.filter_list(self.get_queryset())
        if query:
            search = SearchQuery(query, config="pt_unaccent", search_type="websearch")
            qs = qs.annotate(rank=SearchRank(F("search_vector"), search), similarity=TrigramSimilarity("title", query))
            qs = qs.filter(Q(search_vector=search) | Q(similarity__gt=0.25))
        qs = self.sort_list(qs.distinct(), query)
        page = self.paginate_queryset(qs)
        if query:
            found = snippets([d.id for d in page], query)
            for document in page:
                document.snippet = found.get(str(document.id))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(tags=["Documentos"])
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["Documentos"],
        request={"multipart/form-data": UploadSerializer},
        responses={201: OpenApiTypes.OBJECT},
        description="Envia um ou mais arquivos PDF/DOCX (campo `files`, repetido). Arquivos iguais aos que você já tem "
        "não são duplicados: voltam com `duplicate: true`.",
    )
    def create(self, request, *args, **kwargs):
        files = request.FILES.getlist("files")
        if not files:
            raise ApiError("Envie pelo menos um arquivo no campo files.")
        if len(files) > settings.MAX_FILES_PER_UPLOAD:
            raise ApiError(f"Envie no máximo {settings.MAX_FILES_PER_UPLOAD} arquivos por vez.")
        visibility = request.data.get("visibility") or Document.Visibility.PRIVATE
        if visibility not in Document.Visibility.values:
            raise ApiError("Visibilidade inválida.")
        collection = None
        if request.data.get("collection"):
            collection = get_object_or_404(Collection, pk=request.data["collection"], owner=request.user)
        items, errors = [], []
        for uploaded in files:
            try:
                result = services.store_upload(request.user, uploaded, visibility, collection)
            except services.UploadRejected as exc:
                errors.append({"file": uploaded.name, "message": str(exc)})
                continue
            document = with_relations(Document.objects.filter(pk=result.document.pk), request.user).get()
            items.append({**DocumentSerializer(document, context={"request": request}).data, "duplicate": result.duplicate})
        code = status.HTTP_201_CREATED if items else status.HTTP_400_BAD_REQUEST
        return Response({"items": items, "errors": errors}, status=code)

    @extend_schema(tags=["Documentos"], request=DocumentSerializer)
    def partial_update(self, request, *args, **kwargs):
        document = self.owned_object()
        serializer = DocumentSerializer(document, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        changed = {k for k, v in serializer.validated_data.items() if getattr(document, k) != v}
        was_shared = document.visibility == Document.Visibility.SHARED
        if changed & {"title", "author"}:
            serializer.validated_data["metadata_locked"] = True
        serializer.save()
        if changed & {"title", "author", "description"}:
            services.refresh_search(document.id)
        events.document_event(document)
        if was_shared and document.visibility == Document.Visibility.PRIVATE:
            events.publish(document.owner_id, "document.deleted", shared=True, id=str(document.id), only_shared=True)
        return Response(DocumentDetailSerializer(self.get_object(), context={"request": request}).data)

    @extend_schema(exclude=True)
    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @extend_schema(tags=["Documentos"], description="Apaga o documento, os arquivos e as anotações.")
    def destroy(self, request, *args, **kwargs):
        services.delete_document(self.owned_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["Arquivos"],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
        parameters=[OpenApiParameter("download", bool, description="Força o download (Content-Disposition)")],
        description="Arquivo original. Aceita o cabeçalho Range (o leitor de PDF baixa só o que precisa).",
    )
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        document = self.get_object()
        if not document.file_path.exists():
            raise Http404
        download = request.query_params.get("download") in {"1", "true"}
        return file_response(request, document.file_path, document.mime_type, document.original_name, download)

    @extend_schema(tags=["Arquivos"], responses={(200, "image/jpeg"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def cover(self, request, pk=None):
        document = self.get_object()
        if not document.cover_path.exists():
            raise Http404
        return file_response(request, document.cover_path, "image/jpeg", cache_control="private, max-age=31536000")

    @extend_schema(
        tags=["Arquivos"],
        responses=OpenApiTypes.OBJECT,
        description="HTML de leitura dos arquivos DOCX (já higienizado) e o sumário.",
    )
    @action(detail=True, methods=["get"])
    def reader(self, request, pk=None):
        document = self.get_object()
        if not document.has_reader_html or not document.reader_path.exists():
            raise ApiError("Este documento não tem versão em HTML.", "not_found", 404)
        return Response({"html": document.reader_path.read_text(encoding="utf-8"), "outline": document.outline})

    @extend_schema(tags=["Arquivos"], responses={(200, "image/*"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path=r"media/(?P<name>[^/]+)")
    def media(self, request, pk=None, name=None):
        document = self.get_object()
        if not MEDIA_NAME.match(name or ""):
            raise Http404
        path = (document.folder / "media" / name).resolve()
        if not path.is_relative_to(document.folder.resolve()) or not path.is_file():
            raise Http404
        types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}
        content_type = types.get(path.suffix.lower(), "application/octet-stream")
        return file_response(request, path, content_type, cache_control="private, max-age=86400")

    @extend_schema(tags=["Processamento"], request=None, responses=DocumentSerializer)
    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        document = self.owned_object()
        if document.status in PROCESSING and document.attempts and document.status != Document.Status.QUEUED:
            raise ApiError("O documento já está sendo processado.", "conflict", 409)
        services.requeue(document, "extract")
        return Response(DocumentSerializer(self.get_object(), context={"request": request}).data)

    @extend_schema(
        tags=["Processamento"],
        request=None,
        responses=DocumentSerializer,
        description="Gera a descrição por IA de novo (útil depois de trocar o provedor).",
    )
    @action(detail=True, methods=["post"])
    def describe(self, request, pk=None):
        document = self.owned_object()
        if document.status != Document.Status.READY:
            raise ApiError("Espere o documento terminar de processar.", "conflict", 409)
        services.requeue(document, "describe")
        return Response(DocumentSerializer(self.get_object(), context={"request": request}).data)

    @extend_schema(tags=["Documentos"], request=TagsInputSerializer, responses=DocumentSerializer)
    @action(detail=True, methods=["put"])
    def tags(self, request, pk=None):
        document = self.owned_object()
        data = TagsInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_tags(document, data.validated_data["tags"])
        services.refresh_search(document.id)
        events.document_event(document)
        return Response(DocumentSerializer(self.get_object(), context={"request": request}).data)

    @extend_schema(methods=["GET"], tags=["Leitura"], responses=ReadingSerializer)
    @extend_schema(methods=["PUT", "PATCH"], tags=["Leitura"], request=ReadingSerializer, responses=ReadingSerializer)
    @action(detail=True, methods=["get", "put", "patch"])
    def reading(self, request, pk=None):
        document = self.get_object()
        state = ReadingState.objects.filter(user=request.user, document=document).first()
        if request.method == "GET":
            return Response(ReadingSerializer(state).data if state else ReadingSerializer(ReadingState()).data)
        serializer = ReadingSerializer(state or ReadingState(user=request.user, document=document), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        now = timezone.now()
        data = serializer.validated_data
        shelf = data.get("shelf")
        if shelf == ReadingState.Shelf.READING and not (state and state.started_at):
            data["started_at"] = now
        if shelf == ReadingState.Shelf.DONE:
            data["finished_at"] = now
        elif shelf is not None:
            data["finished_at"] = None
        if document.page_count and data.get("page"):
            data["page"] = min(data["page"], document.page_count)
        state = serializer.save()
        events.publish(request.user.id, "reading.updated", id=str(document.id))
        return Response(ReadingSerializer(state).data)

    @extend_schema(
        tags=["Leitura"],
        request=None,
        responses=ReadingSerializer,
        description="Registra que o documento foi aberto no leitor: atualiza o “continuar lendo” e move para “Lendo”.",
    )
    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        document = self.get_object()
        now = timezone.now()
        with transaction.atomic():
            state, _ = ReadingState.objects.select_for_update().get_or_create(user=request.user, document=document)
            state.last_opened_at = now
            if state.shelf in {"", ReadingState.Shelf.TO_READ}:
                state.shelf = ReadingState.Shelf.READING
                state.started_at = state.started_at or now
            state.save()
        events.publish(request.user.id, "reading.updated", id=str(document.id))
        return Response(ReadingSerializer(state).data)

    @extend_schema(methods=["GET"], tags=["Leitura"], responses=AnnotationSerializer(many=True))
    @extend_schema(methods=["POST"], tags=["Leitura"], request=AnnotationSerializer, responses=AnnotationSerializer)
    @action(detail=True, methods=["get", "post"])
    def annotations(self, request, pk=None):
        document = self.get_object()
        if request.method == "GET":
            items = Annotation.objects.filter(user=request.user, document=document)
            return Response(AnnotationSerializer(items, many=True).data)
        if Annotation.objects.filter(user=request.user, document=document).count() >= 2000:
            raise ApiError("Limite de anotações neste documento atingido.")
        serializer = AnnotationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, document=document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Leitura"])
class AnnotationViewSet(mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = AnnotationSerializer
    http_method_names = ["patch", "delete"]

    def get_queryset(self):
        return Annotation.objects.filter(user=self.request.user)


@extend_schema(tags=["Coleções"])
class CollectionViewSet(viewsets.ModelViewSet):
    serializer_class = CollectionSerializer
    http_method_names = ["get", "post", "patch", "put", "delete"]

    def get_queryset(self):
        return (
            Collection.objects.filter(owner=self.request.user)
            .annotate(document_count=Count("items"))
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=CollectionItem.objects.select_related("document").order_by("position", "added_at"),
                    to_attr="preview_items",
                )
            )
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        events.publish(self.request.user.id, "collections.changed")

    def perform_update(self, serializer):
        serializer.save()
        events.publish(self.request.user.id, "collections.changed")

    def perform_destroy(self, instance):
        instance.delete()
        events.publish(self.request.user.id, "collections.changed")

    @extend_schema(exclude=True)
    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    @extend_schema(request=CollectionDocumentsSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def documents(self, request, pk=None):
        collection = self.get_object()
        data = CollectionDocumentsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        documents = list(visible_documents(request.user).filter(pk__in=data.validated_data["document_ids"]))
        added = services.add_to_collection(collection, documents)
        events.publish(request.user.id, "collections.changed")
        return Response({"added": added})

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=rf"documents/(?P<document_id>{UUID_PATH})")
    def remove_document(self, request, pk=None, document_id=None):
        collection = self.get_object()
        CollectionItem.objects.filter(collection=collection, document_id=document_id).delete()
        events.publish(request.user.id, "collections.changed")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=CollectionDocumentsSerializer, responses={204: None})
    @action(detail=True, methods=["put"])
    def order(self, request, pk=None):
        collection = self.get_object()
        data = CollectionDocumentsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        positions = {str(doc_id): index for index, doc_id in enumerate(data.validated_data["document_ids"], start=1)}
        with transaction.atomic():
            for item in collection.items.select_for_update():
                item.position = positions.get(str(item.document_id), len(positions) + item.position)
                item.save(update_fields=["position"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TagListView(APIView):
    @extend_schema(tags=["Documentos"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        tags = (
            Tag.objects.filter(owner=request.user)
            .annotate(count=Count("document_tags"))
            .filter(count__gt=0)
            .order_by("-count", "name")[:200]
        )
        return Response([{"name": t.name, "slug": t.slug, "count": t.count} for t in tags])


class StatsView(APIView):
    @extend_schema(tags=["Documentos"], responses=OpenApiTypes.OBJECT, description="Contagens para o menu lateral.")
    def get(self, request):
        user = request.user
        mine = Document.objects.filter(owner=user)
        counts = mine.aggregate(
            total=Count("id"),
            pdf=Count("id", filter=Q(kind="pdf")),
            docx=Count("id", filter=Q(kind="docx")),
            processing=Count("id", filter=Q(status__in=PROCESSING)),
            failed=Count("id", filter=Q(status="failed")),
        )
        shelves = dict(
            ReadingState.objects.filter(user=user)
            .exclude(shelf="")
            .filter(document__in=visible_documents(user))
            .values_list("shelf")
            .annotate(n=Count("id"))
        )
        favorites = ReadingState.objects.filter(user=user, favorite=True, document__in=visible_documents(user)).count()
        shared = Document.objects.filter(visibility="shared").exclude(owner=user).count()
        recent = (
            ReadingState.objects.filter(user=user, last_opened_at__isnull=False, document__in=visible_documents(user))
            .select_related("document")
            .order_by("-last_opened_at")[:4]
        )
        continue_reading = [
            {
                "id": str(s.document_id),
                "title": s.document.title,
                "kind": s.document.kind,
                "page": s.page,
                "page_count": s.document.page_count,
                "progress": s.progress,
                "cover_url": f"/api/v1/documents/{s.document_id}/cover?v={s.document.cover_version}"
                if s.document.has_cover
                else None,
                "cover_color": s.document.cover_color,
            }
            for s in recent
        ]
        return Response(
            {
                **counts,
                "shared": shared,
                "favorites": favorites,
                "shelves": {k: shelves.get(k, 0) for k in ReadingState.Shelf.values},
                "continue_reading": continue_reading,
            }
        )
