"""
Postgres-backed storage via Django ORM (shared swecc Postgres / Supabase).

Callers must call django.setup() before using this module (bench-api and
bench-worker set DJANGO_SETTINGS_MODULE and bootstrap at startup).
"""

from bench_common.storage.django_store import *  # noqa: F403
