#!/usr/bin/env python
"""Fail CI when bench models changed without a committed migration."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test_db")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("SENDGRID_API_KEY", "test")
os.environ.setdefault("SUPABASE_URL", "http://test")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("METRIC_SERVER_URL", "http://test")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("AWS_BUCKET_NAME", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("INTERNSHIP_CHANNEL_ID", "123456")
os.environ.setdefault("NEW_GRAD_CHANNEL_ID", "123456")

import django
from django.conf import settings
from django.core.management import call_command

settings.DATABASES["default"] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
}

django.setup()

if __name__ == "__main__":
    call_command("makemigrations", "bench", check=True, dry_run=True, verbosity=1)
