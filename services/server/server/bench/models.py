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
    data = models.JSONField()
    published = models.BooleanField(default=False)

    class Meta:
        app_label = "bench"


class RunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Run(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    domain = models.ForeignKey(
        Domain,
        on_delete=models.PROTECT,
        db_column="domain_id",
        to_field="id",
        related_name="runs",
    )
    status = models.CharField(
        max_length=64,
        choices=RunStatus.choices,
        default=RunStatus.PENDING,
        db_index=True,
    )
    data = models.JSONField()

    class Meta:
        app_label = "bench"


class EpisodeStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    TIMEOUT = "timeout", "Timeout"


class Episode(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        db_column="run_id",
        to_field="id",
        related_name="episodes",
    )
    status = models.CharField(
        max_length=64,
        choices=EpisodeStatus.choices,
        default=EpisodeStatus.PENDING,
        db_index=True,
    )
    data = models.JSONField()

    class Meta:
        app_label = "bench"


class Leaderboard(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        db_column="domain_id",
        to_field="id",
        related_name="leaderboard_entries",
    )
    run = models.OneToOneField(
        Run,
        on_delete=models.CASCADE,
        db_column="run_id",
        to_field="id",
        related_name="leaderboard_entry",
    )
    model = models.CharField(max_length=255)
    primary_score = models.FloatField()
    data = models.JSONField()

    class Meta:
        app_label = "bench"


class DeveloperEnvironmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CLONING = "cloning", "Cloning"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class DeveloperEnvironment(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    owner_id = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(default="", blank=True)
    github_url = models.URLField(max_length=512)
    status = models.CharField(
        max_length=64,
        choices=DeveloperEnvironmentStatus.choices,
        default=DeveloperEnvironmentStatus.PENDING,
        db_index=True,
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="domain_id",
        to_field="id",
        related_name="developer_environments",
    )
    env_url = models.URLField(max_length=512, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "bench"


class BenchJobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class BenchJob(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    environment = models.ForeignKey(
        DeveloperEnvironment,
        on_delete=models.CASCADE,
        db_column="env_id",
        to_field="id",
        related_name="bench_jobs",
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="domain_id",
        to_field="id",
        related_name="bench_jobs",
    )
    github_url = models.URLField(max_length=512)
    status = models.CharField(
        max_length=64,
        choices=BenchJobStatus.choices,
        default=BenchJobStatus.QUEUED,
        db_index=True,
    )
    model_results = models.JSONField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "bench"


class EnvironmentUsage(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        db_column="domain_id",
        to_field="id",
        related_name="usage_records",
    )
    run = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        db_column="run_id",
        to_field="id",
        related_name="usage_records",
    )
    model = models.CharField(max_length=255)
    episode_count = models.IntegerField(default=0)
    primary_score = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "bench"
