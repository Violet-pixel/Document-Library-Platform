from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.accounts.models import ApiToken


class BearerTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode(errors="ignore")
        if not header.startswith(self.keyword + " "):
            return None
        raw = header[len(self.keyword) + 1 :].strip()
        if not raw.startswith(ApiToken.PREFIX + "_"):
            raise exceptions.AuthenticationFailed("Token inválido.")
        try:
            token = ApiToken.objects.select_related("user").get(token_hash=ApiToken.hash(raw))
        except ApiToken.DoesNotExist:
            raise exceptions.AuthenticationFailed("Token inválido.") from None
        if not token.is_valid or not token.user.is_active:
            raise exceptions.AuthenticationFailed("Token expirado ou revogado.")
        now = timezone.now()
        if not token.last_used_at or (now - token.last_used_at).total_seconds() > 60:
            ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
        return token.user, token

    def authenticate_header(self, request):
        return self.keyword
