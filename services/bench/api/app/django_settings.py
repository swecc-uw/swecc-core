"""
Minimal Django settings used by bench-api in standalone mode.

bench-api does not run any Django views/middleware/templates/admin — it is a
FastAPI app that only uses Django's ORM to talk to the bench schema (which is
provisioned by swecc-server's `manage.py migrate` on startup). These settings
contain just enough to make `django.setup()` happy and `apps.bench` importable.

Production Swarm deploy uses Docker config ``server_env`` (same as swecc-server).

Shared with server (intentional — same Postgres): DB_HOST, DB_NAME, DB_PORT,
DB_USER, DB_PASSWORD (see services/server/server/server/settings.py).

Bench-only runtime config uses ORCH_* (see bench_common.config.Settings).
Do not set DJANGO_SETTINGS_MODULE in server_env — bench-api forces its own.
"""

import os

# Same keys as services/server/server/server/settings.py
DB_HOST = os.environ["DB_HOST"]
DB_NAME = os.environ["DB_NAME"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

# Django requires SECRET_KEY; bench ORM-only — reuse JWT_SECRET from server_env.
SECRET_KEY = os.environ["JWT_SECRET"]

DEBUG = False

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "bench.apps.BenchConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
