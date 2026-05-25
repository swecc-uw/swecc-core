"""Delete expired guest sessions and guest runs past expires_at."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from bench.models import ActorType, BenchGuestSession, Run


class Command(BaseCommand):
    help = "Remove expired bench guest sessions and expired guest runs"

    def handle(self, *args, **options):
        now = timezone.now()
        session_count, _ = BenchGuestSession.objects.filter(expires_at__lt=now).delete()
        run_count, _ = Run.objects.filter(
            actor_type=ActorType.GUEST,
            expires_at__lt=now,
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {session_count} guest sessions, {run_count} guest runs")
        )
