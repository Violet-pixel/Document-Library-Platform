from django.core.management.base import BaseCommand

from apps.processing.worker import Worker


class Command(BaseCommand):
    help = "Processa os documentos enviados: leitura pelo processador Java e descrição por IA."

    def add_arguments(self, parser):
        parser.add_argument("--stages", default="extract,describe", help="Etapas que este worker consome.")
        parser.add_argument("--threads", type=int, default=None, help="Documentos processados ao mesmo tempo.")

    def handle(self, *args, stages, threads, **options):
        names = [s.strip() for s in stages.split(",") if s.strip() in {"extract", "describe"}]
        Worker(names or ["extract", "describe"], threads).run()
