from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import health

urlpatterns = [
    path("api/health", health, name="health"),
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/v1/", include("config.api_urls")),
    path("", include("apps.library.pages")),
]
