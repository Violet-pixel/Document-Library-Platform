from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db.models import Count
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import throttle
from apps.accounts.models import ApiToken, User
from apps.accounts.serializers import (
    AdminUserSerializer,
    LoginSerializer,
    PasswordSerializer,
    SignupSerializer,
    TokenSerializer,
    UserSerializer,
)
from apps.core.api import ApiError


class IsAdmin(permissions.BasePermission):
    message = "Apenas administradores."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(request=LoginSerializer, responses=UserSerializer, tags=["Autenticação"])
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email, password = data.validated_data["email"], data.validated_data["password"]
        ip = throttle.client_ip(request)
        if throttle.blocked(ip, email):
            raise ApiError("Muitas tentativas. Aguarde 15 minutos e tente de novo.", "throttled", 429)
        user = authenticate(request, email=email, password=password)
        if user is None:
            throttle.fail(ip, email)
            raise ApiError("E-mail ou senha incorretos.", "invalid_credentials", 400)
        throttle.reset(ip, email)
        login(request, user)
        return Response(UserSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class SignupView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(request=SignupSerializer, responses=UserSerializer, tags=["Autenticação"])
    def post(self, request):
        if not settings.ALLOW_SIGNUP:
            raise ApiError("O cadastro está desativado nesta instalação.", "signup_disabled", 403)
        data = SignupSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = User.objects.create_user(
            email=data.validated_data["email"], password=data.validated_data["password"], name=data.validated_data["name"]
        )
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None}, tags=["Autenticação"])
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(responses={204: None}, tags=["Autenticação"])
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    @extend_schema(tags=["Minha conta"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=["Minha conta"])
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(exclude=True)
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)


class PasswordView(APIView):
    @extend_schema(request=PasswordSerializer, responses={204: None}, tags=["Minha conta"])
    def post(self, request):
        data = PasswordSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        request.user.set_password(data.validated_data["new"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Minha conta"])
class TokenViewSet(viewsets.ModelViewSet):
    serializer_class = TokenSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return ApiToken.objects.filter(user=self.request.user, revoked_at__isnull=True)

    def create(self, request, *args, **kwargs):
        data = TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if self.get_queryset().count() >= 20:
            raise ApiError("Limite de 20 tokens ativos. Revogue algum antes de criar outro.")
        token, raw = ApiToken.issue(request.user, data.validated_data["name"], data.validated_data.get("expires_at"))
        return Response({**TokenSerializer(token).data, "token": raw}, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        token = self.get_object()
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Administração"])
class UserAdminViewSet(viewsets.ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return User.objects.annotate(document_count=Count("documents")).order_by("name")

    def perform_update(self, serializer):
        user = serializer.instance
        if user == self.request.user and (
            serializer.validated_data.get("role", user.role) != User.Role.ADMIN
            or serializer.validated_data.get("is_active", True) is False
        ):
            raise ApiError("Você não pode remover o próprio acesso de administrador.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise ApiError("Você não pode excluir a própria conta por aqui.")
        from apps.library.services import delete_document_files

        for document in instance.documents.all():
            delete_document_files(document)
        instance.delete()
