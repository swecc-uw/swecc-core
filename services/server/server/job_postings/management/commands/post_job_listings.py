import os
import sys

from django.core.management.base import BaseCommand, CommandError
from job_postings.run import run


class Command(BaseCommand):
    help = "Posts new SimplifyJobs internship and new grad listings to Discord"

    def handle(self, *args, **options):
        result = run(os.environ)

        # Report stats
        parts = []
        if result.sent > 0:
            parts.append(f"{result.sent} sent")
        if result.deferred > 0:
            parts.append(f"{result.deferred} deferred")
        if result.dead > 0:
            parts.append(f"{result.dead} dead-lettered")
        if result.stale_recovered > 0:
            parts.append(f"{result.stale_recovered} stale leases recovered")

        if parts:
            self.stdout.write(f"Delivery: {', '.join(parts)}")
        else:
            self.stdout.write("No messages to deliver")

        # Exit nonzero if any failures
        if result.failed:
            error_parts = []
            if result.enqueue_errors:
                error_parts.append(
                    f"Enqueue failures: {'; '.join(str(e) for e in result.enqueue_errors)}"
                )
            if result.dead > 0:
                error_parts.append(f"{result.dead} message(s) dead-lettered")
            raise CommandError("; ".join(error_parts))

        self.stdout.write(self.style.SUCCESS("Checked all listing sources"))
