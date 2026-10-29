from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ApiToken

pytestmark = pytest.mark.django_db


def test_login_and_me(user):
    client = APIClient()
    response = client.post("/api/v1/auth/login", {"email": "ANA@exemplo.dev", "password": "Senha-forte-123"}, format="json")
    assert response.status_code == 200
    assert response.json()["email"] == "ana@exemplo.dev"
    assert client.get("/api/v1/me").json()["name"] == "Ana Souza"


def test_login_wrong_password_is_blocked_after_five_attempts(user):
    client = APIClient()
    for _ in range(5):
        response = client.post("/api/v1/auth/login", {"email": user.email, "password": "errada"}, format="json")
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_credentials"
    response = client.post("/api/v1/auth/login", {"email": user.email, "password": "Senha-forte-123"}, format="json")
    assert response.status_code == 429


def test_login_requires_csrf_token(user):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post("/api/v1/auth/login", {"email": user.email, "password": "Senha-forte-123"}, format="json")
    assert response.status_code == 403
    client.get("/api/v1/auth/csrf")
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/api/v1/auth/login", {"email": user.email, "password": "Senha-forte-123"}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200


def test_anonymous_cannot_use_api():
    response = APIClient().get("/api/v1/documents")
    assert response.status_code in (401, 403)
    assert response.json()["error"] == "not_authenticated"


def test_signup(settings, db):
    client = APIClient()
    data = {"name": "Nova Pessoa", "email": "nova@exemplo.dev", "password": "Outra-senha-456"}
    assert client.post("/api/v1/auth/signup", data, format="json").status_code == 201
    assert client.get("/api/v1/me").status_code == 200
    settings.ALLOW_SIGNUP = False
    data["email"] = "outra@exemplo.dev"
    assert APIClient().post("/api/v1/auth/signup", data, format="json").status_code == 403


def test_signup_rejects_weak_password(db):
    data = {"name": "Nova Pessoa", "email": "nova@exemplo.dev", "password": "123"}
    response = APIClient().post("/api/v1/auth/signup", data, format="json")
    assert response.status_code == 400


def test_update_profile_and_password(api, user):
    assert api.patch("/api/v1/me", {"theme": "dark", "name": "Ana S."}, format="json").json()["theme"] == "dark"
    response = api.post("/api/v1/me/password", {"current": "errada", "new": "Nova-senha-789"}, format="json")
    assert response.status_code == 400
    response = api.post("/api/v1/me/password", {"current": "Senha-forte-123", "new": "Nova-senha-789"}, format="json")
    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password("Nova-senha-789")


def test_personal_token_lifecycle(api, user):
    created = api.post("/api/v1/me/tokens", {"name": "script de backup"}, format="json").json()
    raw = created["token"]
    assert raw.startswith("dl_")
    stored = ApiToken.objects.get(pk=created["id"])
    assert stored.token_hash != raw and raw not in stored.token_hash

    client = APIClient()
    assert client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 200
    assert client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer dl_x_invalido").status_code == 401

    assert api.delete(f"/api/v1/me/tokens/{created['id']}").status_code == 204
    assert client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code == 401


def test_token_cannot_be_created_already_expired(api):
    past = (timezone.now() - timedelta(days=1)).isoformat()
    response = api.post("/api/v1/me/tokens", {"name": "antigo", "expires_at": past}, format="json")
    assert response.status_code == 400 and "expires_at" in response.json()["fields"]
    future = (timezone.now() + timedelta(days=30)).isoformat()
    assert api.post("/api/v1/me/tokens", {"name": "novo", "expires_at": future}, format="json").status_code == 201


def test_users_admin_only(api, admin, api_for, user):
    assert api.get("/api/v1/users").status_code == 403
    admin_client = api_for(admin)
    listing = admin_client.get("/api/v1/users").json()
    assert {u["email"] for u in listing} >= {user.email, admin.email}
    created = admin_client.post(
        "/api/v1/users", {"email": "novo@exemplo.dev", "name": "Novo", "password": "Senha-nova-321"}, format="json"
    )
    assert created.status_code == 201
    response = admin_client.patch(f"/api/v1/users/{admin.id}", {"role": "member"}, format="json")
    assert response.status_code == 400
    assert admin_client.delete(f"/api/v1/users/{created.json()['id']}").status_code == 204
