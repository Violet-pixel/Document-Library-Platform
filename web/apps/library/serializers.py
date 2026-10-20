from rest_framework import serializers

from apps.library.models import Annotation, Collection, Document, ReadingState


class OwnerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    initials = serializers.CharField()


class ReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingState
        fields = ["shelf", "page", "progress", "location", "favorite", "started_at", "finished_at", "last_opened_at"]
        read_only_fields = ["started_at", "finished_at", "last_opened_at"]

    def validate_progress(self, value):
        return min(max(float(value), 0.0), 1.0)

    def validate_location(self, value):
        if not isinstance(value, dict) or len(str(value)) > 1000:
            raise serializers.ValidationError("Posição inválida.")
        return value


EMPTY_READING = {
    "shelf": "",
    "page": 1,
    "progress": 0,
    "location": {},
    "favorite": False,
    "started_at": None,
    "finished_at": None,
    "last_opened_at": None,
}


class DocumentSerializer(serializers.ModelSerializer):
    owner = OwnerSerializer(read_only=True)
    is_owner = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    cover_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    reading = serializers.SerializerMethodField()
    collections = serializers.SerializerMethodField()
    snippet = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "author",
            "description",
            "summary",
            "summary_source",
            "summary_model",
            "summary_at",
            "kind",
            "original_name",
            "size_bytes",
            "page_count",
            "word_count",
            "language",
            "cover_url",
            "cover_width",
            "cover_height",
            "cover_color",
            "cover_generated",
            "has_reader_html",
            "file_url",
            "status",
            "status_label",
            "status_detail",
            "visibility",
            "owner",
            "is_owner",
            "tags",
            "collections",
            "reading",
            "snippet",
            "created_at",
            "updated_at",
            "processed_at",
        ]
        read_only_fields = [f for f in fields if f not in {"title", "author", "description", "visibility"}]

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_is_owner(self, obj) -> bool:
        user = self._user()
        return bool(user and obj.owner_id == user.id)

    def get_cover_url(self, obj) -> str | None:
        if not obj.has_cover:
            return None
        return f"/api/v1/documents/{obj.id}/cover?v={obj.cover_version}"

    def get_file_url(self, obj) -> str:
        return f"/api/v1/documents/{obj.id}/file"

    def get_tags(self, obj) -> list[dict]:
        items = getattr(obj, "prefetched_tags", None)
        if items is None:
            items = obj.document_tags.select_related("tag").all()
        return [{"name": dt.tag.name, "slug": dt.tag.slug, "source": dt.source} for dt in items]

    def get_reading(self, obj) -> dict:
        states = getattr(obj, "my_reading", None)
        if states is None:
            user = self._user()
            states = list(obj.reading_states.filter(user=user)) if user else []
        return ReadingSerializer(states[0]).data if states else dict(EMPTY_READING)

    def get_collections(self, obj) -> list[str]:
        if not self.get_is_owner(obj):
            return []
        items = getattr(obj, "prefetched_items", None)
        if items is None:
            items = obj.collection_items.all()
        return [str(item.collection_id) for item in items]

    def get_snippet(self, obj) -> str | None:
        return getattr(obj, "snippet", None)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("O título não pode ficar vazio.")
        return value


class DocumentDetailSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["outline", "metadata", "sha256", "attempts"]
        read_only_fields = DocumentSerializer.Meta.read_only_fields + ["outline", "metadata", "sha256", "attempts"]


class TagsInputSerializer(serializers.Serializer):
    tags = serializers.ListField(child=serializers.CharField(max_length=40), max_length=12)


class UploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField(), allow_empty=False)
    visibility = serializers.ChoiceField(choices=Document.Visibility.choices, required=False)
    collection = serializers.UUIDField(required=False)


class CollectionSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True)
    covers = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = ["id", "name", "description", "document_count", "covers", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        request = self.context["request"]
        qs = Collection.objects.filter(owner=request.user, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Você já tem uma coleção com esse nome.")
        return value

    def get_covers(self, obj) -> list[dict]:
        items = getattr(obj, "preview_items", None)
        if items is None:
            items = obj.items.select_related("document")[:4]
        result = []
        for item in items[:4]:
            doc = item.document
            result.append(
                {
                    "id": str(doc.id),
                    "url": f"/api/v1/documents/{doc.id}/cover?v={doc.cover_version}" if doc.has_cover else None,
                    "color": doc.cover_color,
                    "title": doc.title,
                }
            )
        return result


class CollectionDocumentsSerializer(serializers.Serializer):
    document_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=500)


class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = ["id", "document", "kind", "page", "anchor", "quote", "note", "color", "created_at", "updated_at"]
        read_only_fields = ["id", "document", "created_at", "updated_at"]

    def validate_anchor(self, value):
        if not isinstance(value, dict) or len(str(value)) > 8000:
            raise serializers.ValidationError("Âncora inválida.")
        return value

    def validate_color(self, value):
        if value not in {"salvia", "rose", "ardosia", "camurca"}:
            raise serializers.ValidationError("Cor inválida.")
        return value

    def validate(self, data):
        kind = data.get("kind", getattr(self.instance, "kind", None))
        if kind == Annotation.Kind.NOTE and not (data.get("note") or getattr(self.instance, "note", "")).strip():
            raise serializers.ValidationError({"note": "Escreva a nota."})
        if len(data.get("quote", "")) > 4000 or len(data.get("note", "")) > 8000:
            raise serializers.ValidationError("Texto longo demais.")
        return data
