"""Smoke test: worker module imports with test env configured in conftest."""


def test_worker_module_importable():
    from app import worker

    assert worker.API_URL == "http://localhost:8000"
    assert worker.POLL_INTERVAL == 10
