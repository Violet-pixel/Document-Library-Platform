import hashlib
import secrets
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **fields):
        if not email:
            raise ValueError("Informe o e-mail.")
        user = self.model(email=self.normalize_email(email).lower(), **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **fields):
        fields.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **fields)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(AbstractBaseUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        MEMBER = "member", "Membro"

    class Theme(models.TextChoices):
        SYSTEM = "system", "Sistema"
        LIGHT = "light", "Claro"
        DARK = "dark", "Escuro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("e-mail", max_length=254)
    name = models.CharField("nome", max_length=120)
    role = models.CharField("papel", max_length=10, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField("ativo", default=True)
    theme = models.CharField("tema", max_length=10, choices=Theme.choices, default=Theme.SYSTEM)
    reader_prefs = models.JSONField("preferências do leitor", default=dict, blank=True)
    created_at = models.DateTimeField("criado em", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "accounts_user"
        verbose_name = "usuário"
        constraints = [models.UniqueConstraint(Lower("email"), name="accounts_user_email_unique")]

    def __str__(self):
        return self.email

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        if not parts:
            return self.email[:2].upper()
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


class ApiToken(models.Model):
    """Token pessoal para scripts e integrações. Só o hash fica no banco; o valor aparece uma única vez."""

    PREFIX = "dl"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    name = models.CharField("nome", max_length=80)
    prefix = models.CharField(max_length=12, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_apitoken"
        ordering = ["-created_at"]

    @staticmethod
    def hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, user, name: str, expires_at=None) -> tuple["ApiToken", str]:
        prefix = secrets.token_hex(4)
        raw = f"{cls.PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
        token = cls.objects.create(user=user, name=name, prefix=prefix, token_hash=cls.hash(raw), expires_at=expires_at)
        return token, raw

    @property
    def is_valid(self) -> bool:
        if self.revoked_at:
            return False
        return not (self.expires_at and self.expires_at <= timezone.now())
