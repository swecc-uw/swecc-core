"""Smoke test: worker module imports without WORKER_API_URL crashing the test."""

import os


def test_worker_module_importable(monkeypatch):
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")
    from app import worker

    assert worker.API_URL == "http://localhost:8000"
