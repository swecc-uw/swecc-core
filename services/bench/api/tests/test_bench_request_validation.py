from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "services" / "server" / "server"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import django
from django.apps import apps

if not apps.ready:
    django.setup()

from app.routes.bench import TestBenchRequest as BenchRequest


def test_dev_bench_request_rejects_silent_multi_episode_request() -> None:
    with pytest.raises(ValidationError):
        BenchRequest(
            env_id="env-1", model="gemini/gemini-3.1-flash-lite", num_episodes=2
        )


def test_dev_bench_request_accepts_explicit_single_episode() -> None:
    req = BenchRequest(
        env_id="env-1", model="gemini/gemini-3.1-flash-lite", num_episodes=1
    )
    assert req.num_episodes == 1
