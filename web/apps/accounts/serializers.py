from django.contrib.auth import password_validation
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import ApiToken, User


class UserSerializer(serializers.ModelSerializer):
    initials = serializers.CharField(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "name", "role", "is_admin", "initials", "theme", "reader_prefs", "created_at"]
        read_only_fields = ["id", "email", "role", "created_at"]

    def validate_reader_prefs(self, value):
        if not isinstance(value, dict) or len(str(value)) > 2000:
            raise serializers.ValidationError("Preferências inválidas.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class SignupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Já existe uma conta com este e-mail.")
        return value

    def validate(self, data):
        password_validation.validate_password(data["password"], User(email=data["email"], name=data["name"]))
        return data


class PasswordSerializer(serializers.Serializer):
    current = serializers.CharField(trim_whitespace=False)
    new = serializers.CharField(trim_whitespace=False)

    def validate(self, data):
        user = self.context["request"].user
        if not user.check_password(data["current"]):
            raise serializers.ValidationError({"current": "A senha atual não confere."})
        password_validation.validate_password(data["new"], user)
        return data


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiToken
        fields = ["id", "name", "prefix", "created_at", "last_used_at", "expires_at", "revoked_at"]
        read_only_fields = ["id", "prefix", "created_at", "last_used_at", "revoked_at"]

    def validate_expires_at(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("A data de expiração precisa estar no futuro.")
        return value


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    document_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "name", "role", "is_active", "created_at", "last_login", "password", "document_count"]
        read_only_fields = ["id", "created_at", "last_login"]

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe uma conta com este e-mail.")
        return value

    def validate(self, data):
        if not self.instance and not data.get("password"):
            raise serializers.ValidationError({"password": "Defina uma senha inicial."})
        if data.get("password"):
            password_validation.validate_password(data["password"])
        return data

    def create(self, data):
        password = data.pop("password")
        return User.objects.create_user(password=password, **data)

    def update(self, instance, data):
        password = data.pop("password", None)
        for key, value in data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
