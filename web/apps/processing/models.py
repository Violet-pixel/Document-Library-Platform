from django.db import models
from django.utils import timezone

from apps.library.models import Document


class Job(models.Model):
    """Uma tentativa de uma etapa do processamento. Serve de histórico e de painel de operação."""

    class Stage(models.TextChoices):
        EXTRACT = "extract", "Leitura do arquivo"
        DESCRIBE = "describe", "Descrição por IA"

    class Status(models.TextChoices):
        RUNNING = "running", "Rodando"
        SUCCEEDED = "succeeded", "Concluída"
        RETRYING = "retrying", "Vai tentar de novo"
        FAILED = "failed", "Falhou"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="jobs")
    stage = models.CharField(max_length=10, choices=Stage.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    attempt = models.PositiveSmallIntegerField(default=1)
    worker = models.CharField(max_length=120, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "processing_job"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["document", "-started_at"], name="processing_job_document"),
            models.Index(fields=["status", "-started_at"], name="processing_job_status"),
        ]

    def finish(self, status: str, error: str = "", **details) -> None:
        self.status = status
        self.finished_at = timezone.now()
        self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
        self.error = error[:4000]
        self.details = {**self.details, **details}
        self.save(update_fields=["status", "finished_at", "duration_ms", "error", "details"])
