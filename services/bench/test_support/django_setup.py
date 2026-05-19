"""
Django test bootstrap for bench-api (same strategy as services/server/run_tests.py).

Production uses Postgres via DB_* from server_env. Tests set placeholder env vars,
override DATABASES to SQLite in-memory, run django.setup(), and migrate the bench
app so init_db() and the ORM work without a live database.
"""

from __future__ import annotations

import os


def configure_django_for_tests() -> None:
    from django.apps import apps
    from django.conf import settings

    if apps.ready:
        return

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_NAME", "test_db")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")

    import django
    from django.core.management import call_command

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

    django.setup()

    call_command("migrate", verbosity=0, interactive=False)
