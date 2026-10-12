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


class OutboxMessage(models.Model):
    """
    Transactional outbox for Discord messages.

    Messages are enqueued in the same transaction that marks listings as seen, ensuring atomicity.
    A separate delivery step sends pending messages, handling failures and rate limits gracefully.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DEAD = "dead", "Dead (gave up)"

    source_id = models.CharField(max_length=64, db_index=True)
    webhook_env_var = models.CharField(max_length=64)
    payload = models.JSONField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
        ]

    def __str__(self):
        return f"OutboxMessage {self.id} ({self.source_id}, {self.status})"
