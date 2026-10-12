from django.db import models


class SourceState(models.Model):
    """What has been posted for one listing source. A source with no row has not been seeded."""

    source_id = models.CharField(max_length=64, primary_key=True)
    etag = models.CharField(max_length=255, blank=True)
    # listing id -> date posted (unix seconds)
    seen = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source_id} ({len(self.seen)} seen)"
