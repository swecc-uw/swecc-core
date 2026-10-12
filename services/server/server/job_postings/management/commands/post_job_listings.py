import os

from django.core.management.base import BaseCommand, CommandError
from job_postings.run import run


class Command(BaseCommand):
    help = "Posts new SimplifyJobs internship and new grad listings to Discord"

    def handle(self, *args, **options):
        errors = run(os.environ)
        if errors:
            raise CommandError("; ".join(str(err) for err in errors))
        self.stdout.write(self.style.SUCCESS("Checked all listing sources"))
