from bench.models import (
    BenchJob,
    DeveloperEnvironment,
    Domain,
    EnvironmentUsage,
    Episode,
    Leaderboard,
    Run,
)
from django.contrib import admin


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("id", "published")
    list_filter = ("published",)
    search_fields = ("id",)


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id", "domain_id", "status")
    list_filter = ("status",)
    search_fields = ("id", "domain_id")


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ("id", "run_id", "status")
    list_filter = ("status",)
    search_fields = ("id", "run_id")


@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ("id", "domain_id", "model", "primary_score")
    search_fields = ("domain_id", "model")


@admin.register(DeveloperEnvironment)
class DeveloperEnvironmentAdmin(admin.ModelAdmin):
    list_display = ("id", "owner_id", "name", "status", "domain_id")
    list_filter = ("status",)
    search_fields = ("id", "owner_id", "name", "github_url")


@admin.register(BenchJob)
class BenchJobAdmin(admin.ModelAdmin):
    list_display = ("id", "environment_id", "status", "created_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("id", "environment_id", "github_url")


@admin.register(EnvironmentUsage)
class EnvironmentUsageAdmin(admin.ModelAdmin):
    list_display = ("id", "domain_id", "run_id", "model", "episode_count")
    search_fields = ("domain_id", "model")
