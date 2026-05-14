"""
Bench schema (BenchAnything backend) as Django models.

The bench-api FastAPI service imports these models in standalone mode via
`django.setup()` and queries them through Django's async ORM (Django 4.1+).
swecc-server runs `python manage.py migrate` on startup, so the schema is
provisioned once and shared between both services with zero manual setup.

Most rows store a JSON blob in `data` — the canonical schema lives in the
Pydantic models in bench_common.core.* and is round-tripped through the
ORM layer for storage. Indexed columns are surfaced for query filters.
"""
from django.db import models


class Domain(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    data = models.TextField()
    published = models.BooleanField(default=False)

    class Meta:
        app_label = "bench"


class Run(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    domain_id = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=64, default="pending")
    data = models.TextField()

    class Meta:
        app_label = "bench"


class Episode(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    run_id = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=64, default="pending")
    data = models.TextField()

    class Meta:
        app_label = "bench"


class Leaderboard(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    domain_id = models.CharField(max_length=255, db_index=True)
    run_id = models.CharField(max_length=255, unique=True)
    model = models.CharField(max_length=255)
    primary_score = models.FloatField()
    data = models.TextField()

    class Meta:
        app_label = "bench"


class DeveloperEnvironment(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    owner_id = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(default="", blank=True)
    github_url = models.CharField(max_length=512)
    # pending | cloning | ready | failed
    status = models.CharField(max_length=64, default="pending")
    domain_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    env_url = models.CharField(max_length=512, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.CharField(max_length=64)

    class Meta:
        app_label = "bench"


class BenchJob(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    env_id = models.CharField(max_length=255, db_index=True)
    domain_id = models.CharField(max_length=255, null=True, blank=True)
    github_url = models.CharField(max_length=512)
    # queued | running | completed | failed
    status = models.CharField(max_length=64, default="queued", db_index=True)
    model_results = models.TextField(null=True, blank=True)
    claimed_at = models.CharField(max_length=64, null=True, blank=True)
    completed_at = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.CharField(max_length=64)

    class Meta:
        app_label = "bench"


class EnvironmentUsage(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    domain_id = models.CharField(max_length=255, db_index=True)
    run_id = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    episode_count = models.IntegerField(default=0)
    primary_score = models.FloatField(null=True, blank=True)
    timestamp = models.CharField(max_length=64)

    class Meta:
        app_label = "bench"
