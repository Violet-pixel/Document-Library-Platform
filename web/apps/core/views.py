from django.db import connection
from django.http import JsonResponse

from apps.core import redis as r


def health(request):
    checks = {"db": False, "redis": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["db"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(r.client().ping())
    except Exception:
        pass
    ok = all(checks.values())
    return JsonResponse({"status": "ok" if ok else "degraded", **checks}, status=200 if ok else 503)
