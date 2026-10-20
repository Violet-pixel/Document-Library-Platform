import httpx
import pytest

from apps.processing import processor

pytestmark = pytest.mark.django_db


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200 and response.json() == {"status": "ok", "db": True, "redis": True}


def test_system_requires_admin(api, admin, api_for, settings):
    settings.PROCESSOR_URL = "http://127.0.0.1:9"  # porta fechada: processador fora do ar
    assert api.get("/api/v1/system").status_code == 403
    data = api_for(admin).get("/api/v1/system").json()
    assert data["processor"]["online"] is False
    assert data["ai"]["provider"] == "local"
    assert set(data["documents"]) == {"queued", "extracting", "describing", "ready", "failed"}
    assert api_for(admin).post("/api/v1/system/retry-failed").json() == {"requeued": 0}


def test_processor_health_parsing():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok", "capacity": 2}))
    assert processor.health(transport=transport) == {"online": True, "status": "ok", "capacity": 2}


def test_openapi_schema(api):
    response = api.get("/api/schema")
    assert response.status_code == 200
    assert b"/api/v1/documents" in response.content
