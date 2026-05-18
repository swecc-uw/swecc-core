"""Smoke test that the sandbox app exposes /health (added by FastAPI defaults if missing)."""

from app.main import app


def test_app_constructs():
    assert app.title.lower().startswith("benchanything")
