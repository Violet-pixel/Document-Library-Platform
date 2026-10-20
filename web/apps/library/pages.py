"""Páginas HTML. A aplicação é uma SPA: o Django entrega o esqueleto e o JavaScript monta cada tela pela API."""

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import path, re_path
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.accounts.serializers import UserSerializer
from apps.ai import service as ai


@ensure_csrf_cookie
def login_page(request):
    if request.user.is_authenticated:
        return redirect("/")
    return render(request, "login.html", {"next": request.GET.get("next", "/")})


@login_required
@ensure_csrf_cookie
def app_shell(request, *args, **kwargs):
    boot = {
        "user": UserSerializer(request.user).data,
        "brand": settings.BRAND,
        "maxUploadMb": settings.MAX_UPLOAD_MB,
        "ai": ai.public_config(),
        "staticRoot": settings.STATIC_URL,
    }
    return render(request, "app.html", {"boot": json.dumps(boot, default=str)})


urlpatterns = [
    path("entrar", login_page, name="login-page"),
    path("", app_shell, name="app"),
    re_path(r"^(?:biblioteca|estantes|colecoes|compartilhados|documento|ler|sistema|conta)(?:/.*)?$", app_shell),
]
