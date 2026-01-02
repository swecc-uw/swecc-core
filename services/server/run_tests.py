#!/usr/bin/env python
"""
Test runner script that uses SQLite for testing instead of PostgreSQL.
This allows running tests without a PostgreSQL database.
"""
import os
import sys

# Add server directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    # Set up environment variables
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

    # Override database settings to use SQLite
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=False)

    # Run tests for resume_review and contentManage
    failures = test_runner.run_tests(["resume_review", "contentManage"])
    sys.exit(bool(failures))
