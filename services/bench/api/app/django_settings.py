"""
Minimal Django settings used by bench-api in standalone mode.

bench-api does not run any Django views/middleware/templates/admin — it is a
FastAPI app that only uses Django's ORM to talk to the bench schema (which is
provisioned by swecc-server's `manage.py migrate` on startup). These settings
contain just enough to make `django.setup()` happy and `apps.bench` importable.
"""
import os

# A SECRET_KEY is required by Django even when no views are served. The value
# is irrelevant for ORM-only usage.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "bench-api-orm-only-no-views")

DEBUG = False

# Only the bench app is installed; we don't need contrib.auth/sessions/etc.
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "bench.apps.BenchConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "swecc"),
        "USER": os.environ.get("DB_USER", "swecc"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "swecc-db-instance"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
