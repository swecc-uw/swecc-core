import pytest
from app.auth.policy import assert_guest_can_create_run
from bench_common.config import settings
from fastapi import HTTPException


def test_guest_allowlist_empty_allows_any_domain(monkeypatch):
    monkeypatch.setattr(settings, "demo_domain_ids", [])
    assert_guest_can_create_run("any-domain-id")


def test_guest_allowlist_blocks_non_demo(monkeypatch):
    monkeypatch.setattr(settings, "demo_domain_ids", ["demo-only"])
    with pytest.raises(HTTPException) as exc:
        assert_guest_can_create_run("other")
    assert exc.value.status_code == 403


def test_guest_allowlist_allows_listed_domain(monkeypatch):
    monkeypatch.setattr(settings, "demo_domain_ids", ["demo-only"])
    assert_guest_can_create_run("demo-only")
