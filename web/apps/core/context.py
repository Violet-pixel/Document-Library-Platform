from django.conf import settings


def brand(request):
    return {"BRAND": settings.BRAND, "ALLOW_SIGNUP": settings.ALLOW_SIGNUP, "SEED_DEMO": settings.SEED_DEMO}
