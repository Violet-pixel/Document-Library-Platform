import json
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.library import services
from apps.library.models import Collection, Document, ReadingState

PASSWORD = "Lume@2026"
ACCOUNTS = {
    "admin": {"email": "admin@lume.dev", "name": "Marina Couto", "role": User.Role.ADMIN},
    "leitor": {"email": "leitor@lume.dev", "name": "Rafael Lima", "role": User.Role.MEMBER},
}


class Command(BaseCommand):
    help = "Cria as contas de demonstração e importa os documentos de exemplo (só num banco sem usuários)."

    def handle(self, *args, **options):
        if User.objects.exists():
            self.stdout.write("Já existem contas; demonstração não recriada.")
            return
        users = {
            key: User.objects.create_user(email=a["email"], password=PASSWORD, name=a["name"], role=a["role"])
            for key, a in ACCOUNTS.items()
        }
        manifest_path = settings.EXAMPLES_DIR / "manifest.json"
        if not manifest_path.exists():
            self.stdout.write("Contas criadas; pasta de exemplos não encontrada.")
            return
        items = json.loads(manifest_path.read_text(encoding="utf-8"))
        collections: dict[tuple[str, str], Collection] = {}
        now = timezone.now()
        for index, item in enumerate(items):
            owner = users.get(item.get("owner"), users["admin"])
            path = settings.EXAMPLES_DIR / item["file"]
            if not path.exists():
                continue
            collection = None
            if item.get("collection"):
                key = (owner.email, item["collection"])
                if key not in collections:
                    collections[key], _ = Collection.objects.get_or_create(owner=owner, name=item["collection"])
                collection = collections[key]
            with open(path, "rb") as handle:
                result = services.store_upload(
                    owner, File(handle, name=path.name), item.get("visibility", "private"), collection
                )
            document = result.document
            Document.objects.filter(pk=document.pk).update(created_at=now - timedelta(hours=len(items) - index))
            shelf = item.get("reading_state") or ""
            if shelf or item.get("favorite"):
                page = item.get("progress_page") or 1
                ReadingState.objects.create(
                    user=owner,
                    document=document,
                    shelf=shelf,
                    page=page,
                    progress=1.0 if shelf == "lido" else 0.0,
                    favorite=bool(item.get("favorite")),
                    started_at=now - timedelta(days=3) if shelf in {"lendo", "lido"} else None,
                    finished_at=now - timedelta(days=1) if shelf == "lido" else None,
                    last_opened_at=now - timedelta(minutes=30 * (index + 1)) if shelf == "lendo" else None,
                )
        self.stdout.write(self.style.SUCCESS(f"Demonstração criada: {len(items)} documentos na fila."))
