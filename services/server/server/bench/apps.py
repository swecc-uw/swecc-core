from django.apps import AppConfig


class BenchConfig(AppConfig):
    """Bench schema lives in swecc-core's Django server so a single
    `manage.py migrate` (server entrypoint / local compose) provisions everything.
    Bench-api (FastAPI) imports
    these models in standalone mode via django.setup()."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "bench"
