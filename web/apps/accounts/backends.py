from django.contrib.auth.backends import ModelBackend

from apps.accounts.models import User


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        email = (email or username or "").strip().lower()
        if not email or not password:
            return None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            User().set_password(password)  # mesmo custo de tempo com ou sem usuário
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError):
            return None
        return user if self.user_can_authenticate(user) else None
