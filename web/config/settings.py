"""Configuração do Django. Tudo que muda entre ambientes vem de variáveis de ambiente (veja .env.example)."""

from pathlib import Path

from apps.core.env import env, env_bool, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent

BRAND = {
    "name": "Lume",
    "tagline": "Biblioteca de documentos",
    "version": "1.0.0",
}

SECRET_KEY = env("APP_SECRET_KEY", "dev-inseguro-troque-no-arquivo-env")
DEBUG = env_bool("APP_DEBUG", False)
ALLOWED_HOSTS = env_list("APP_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"])
CSRF_TRUSTED_ORIGINS = env_list("APP_CSRF_TRUSTED_ORIGINS", [])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "channels",
    "apps.core",
    "apps.accounts",
    "apps.library",
    "apps.processing",
    "apps.ai",
    "apps.realtime",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "apps.core.context.brand",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "library"),
        "USER": env("DB_USER", "library"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env_int("DB_PORT", 5432),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"application_name": "web"},
    }
}

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "cache",
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/entrar"
# O e-mail é único sem diferenciar maiúsculas (restrição accounts_user_email_unique sobre lower(email)).
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HTTPS = env_bool("APP_HTTPS", False)
SESSION_COOKIE_SECURE = SECURE_HTTPS
CSRF_COOKIE_SECURE = SECURE_HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if SECURE_HTTPS else None
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = env("APP_TIMEZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
# Arquivos com hash no nome ficam em cache para sempre; os demais (módulos JS importados pelo nome) por 60 s.

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Arquivos dos documentos (volume compartilhado com o worker e o processador Java).
DATA_ROOT = Path(env("DATA_ROOT", str(BASE_DIR.parent / ".data")))
MAX_UPLOAD_MB = env_int("APP_MAX_UPLOAD_MB", 200)
MAX_FILES_PER_UPLOAD = env_int("APP_MAX_FILES_PER_UPLOAD", 50)
FILE_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
FILE_UPLOAD_TEMP_DIR = None

ALLOW_SIGNUP = env_bool("APP_SIGNUP", True)
SEED_DEMO = env_bool("APP_SEED_DEMO", True)
EXAMPLES_DIR = Path(env("APP_EXAMPLES_DIR", str(BASE_DIR.parent / "exemplos")))

PROCESSOR_URL = env("PROCESSOR_URL", "http://localhost:8090")
PROCESSOR_TIMEOUT = env_int("PROCESSOR_TIMEOUT", 300)

PIPELINE = {
    "max_attempts": env_int("PIPELINE_MAX_ATTEMPTS", 4),
    "visibility_timeout": env_int("PIPELINE_VISIBILITY_TIMEOUT", 600),
    "stale_after": env_int("PIPELINE_STALE_AFTER", 1800),
    "worker_threads": env_int("WORKER_THREADS", 2),
}

AI = {
    "provider": env("AI_PROVIDER", "local").lower(),
    "api_key": env("AI_API_KEY", ""),
    "model": env("AI_MODEL", ""),
    "base_url": env("AI_BASE_URL", ""),
    "timeout": env_int("AI_TIMEOUT", 60),
    "max_input_chars": env_int("AI_MAX_INPUT_CHARS", 12000),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.BearerTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": f"{BRAND['name']} API",
    "DESCRIPTION": "API REST da biblioteca de documentos. Autentique com a sessão do navegador ou com um token pessoal "
    "(cabeçalho `Authorization: Bearer <token>`), criado em Minha conta.",
    "VERSION": BRAND["version"],
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
}

CHANNEL_LAYERS = {}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("APP_LOG_LEVEL", "INFO")},
    "loggers": {"django.request": {"level": "ERROR"}, "httpx": {"level": "WARNING"}},
}
