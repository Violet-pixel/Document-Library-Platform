from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.accounts import api as accounts
from apps.library import api as library
from apps.processing import api as processing

router = SimpleRouter(trailing_slash=False)
router.register("documents", library.DocumentViewSet, basename="document")
router.register("annotations", library.AnnotationViewSet, basename="annotation")
router.register("collections", library.CollectionViewSet, basename="collection")
router.register("me/tokens", accounts.TokenViewSet, basename="token")
router.register("users", accounts.UserAdminViewSet, basename="user")

urlpatterns = [
    path("auth/login", accounts.LoginView.as_view(), name="login"),
    path("auth/logout", accounts.LogoutView.as_view(), name="logout"),
    path("auth/signup", accounts.SignupView.as_view(), name="signup"),
    path("auth/csrf", accounts.CsrfView.as_view(), name="csrf"),
    path("me", accounts.MeView.as_view(), name="me"),
    path("me/password", accounts.PasswordView.as_view(), name="password"),
    path("tags", library.TagListView.as_view(), name="tags"),
    path("stats", library.StatsView.as_view(), name="stats"),
    path("system", processing.SystemView.as_view(), name="system"),
    path("system/retry-failed", processing.RetryFailedView.as_view(), name="retry-failed"),
    *router.urls,
]
