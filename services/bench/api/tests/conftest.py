"""Bench-api integration tests use Postgres, matching production."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")


def _postgres_reachable() -> bool:
    try:
        import psycopg

        with psycopg.connect(
            host=os.environ["DB_HOST"],
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            port=int(os.environ["DB_PORT"]),
            connect_timeout=3,
        ):
            return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _postgres_reachable()


def _ensure_django_ready() -> None:
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()


def _reset_bench_tables() -> None:
    from bench.models import BenchTeam, BenchTeamMembership, Domain, Run

    Run.objects.all().delete()
    Domain.objects.all().delete()
    BenchTeamMembership.objects.all().delete()
    BenchTeam.objects.all().delete()


@pytest.fixture(scope="session")
def _bench_schema():
    """Run bench migrations once per session against Postgres."""
    if not POSTGRES_AVAILABLE:
        pytest.skip("Postgres required for bench ORM integration tests (see DB_* env vars)")
    _ensure_django_ready()
    from django.core.management import call_command

    call_command("migrate", "bench", verbosity=0)
    yield


@pytest.fixture
def django_db(_bench_schema):
    """Empty bench tables before/after each integration test."""
    _reset_bench_tables()
    yield
    _reset_bench_tables()


@pytest.fixture
def api_app(django_db):
    from app.main import app

    return app
