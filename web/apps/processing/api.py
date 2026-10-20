from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import IsAdmin
from apps.ai import service as ai
from apps.library import services
from apps.library.models import Document
from apps.processing import processor, queue
from apps.processing.models import Job
from apps.processing.worker import workers_online


def job_data(job: Job) -> dict:
    return {
        "id": job.id,
        "document_id": str(job.document_id),
        "document_title": job.document.title,
        "stage": job.stage,
        "stage_label": job.get_stage_display(),
        "status": job.status,
        "status_label": job.get_status_display(),
        "attempt": job.attempt,
        "worker": job.worker,
        "started_at": job.started_at,
        "duration_ms": job.duration_ms,
        "error": job.error,
        "details": job.details,
    }


class SystemView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Administração"], responses=OpenApiTypes.OBJECT, description="Estado do pipeline e dos serviços.")
    def get(self, request):
        since = timezone.now() - timedelta(hours=24)
        by_status = dict(Document.objects.values_list("status").annotate(n=Count("id")))
        storage = Document.objects.aggregate(bytes=Sum("size_bytes"), count=Count("id"))
        recent = Job.objects.filter(started_at__gte=since)
        day = recent.aggregate(
            succeeded=Count("id", filter=Q(status=Job.Status.SUCCEEDED)),
            failed=Count("id", filter=Q(status=Job.Status.FAILED)),
            retried=Count("id", filter=Q(status=Job.Status.RETRYING)),
            extract_ms=Avg("duration_ms", filter=Q(stage="extract", status=Job.Status.SUCCEEDED)),
            describe_ms=Avg("duration_ms", filter=Q(stage="describe", status=Job.Status.SUCCEEDED)),
        )
        jobs = Job.objects.select_related("document").order_by("-started_at")[:25]
        failures = Document.objects.filter(status=Document.Status.FAILED).order_by("-updated_at")[:20]
        return Response(
            {
                "queues": queue.stats(),
                "workers": workers_online(),
                "processor": processor.health(),
                "ai": ai.public_config(),
                "documents": {s: by_status.get(s, 0) for s in Document.Status.values},
                "storage": {"bytes": storage["bytes"] or 0, "count": storage["count"]},
                "last_24h": {k: (round(v) if isinstance(v, float) else v) for k, v in day.items()},
                "jobs": [job_data(j) for j in jobs],
                "failures": [
                    {"id": str(d.id), "title": d.title, "detail": d.status_detail, "updated_at": d.updated_at}
                    for d in failures
                ],
            }
        )


class RetryFailedView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(tags=["Administração"], request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        count = 0
        for document in Document.objects.filter(status=Document.Status.FAILED)[:500]:
            services.requeue(document, "extract")
            count += 1
        return Response({"requeued": count})
