import os

from bench_common.config import Settings


def test_mq_enabled_keeps_orphan_reaper_enabled_by_default(monkeypatch):
    monkeypatch.setenv("ORCH_MQ_ENABLED", "1")
    s = Settings()
    assert s.mq_enabled is True
    assert s.enable_orphan_reaper is True


def test_orphan_reaper_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setenv("ORCH_MQ_ENABLED", "1")
    monkeypatch.setenv("ORCH_ENABLE_ORPHAN_REAPER", "false")
    s = Settings()
    assert s.mq_enabled is True
    assert s.enable_orphan_reaper is False


def test_bench_mq_prefetch_override(monkeypatch):
    monkeypatch.delenv("ORCH_MQ_ENABLED", raising=False)
    monkeypatch.setenv("BENCH_MQ_PREFETCH", "5")
    s = Settings()
    assert s.mq_prefetch == 5


def test_stale_watchdog_defaults_enabled(monkeypatch):
    monkeypatch.delenv("ORCH_ENABLE_STALE_WATCHDOG", raising=False)
    s = Settings()
    assert s.enable_stale_watchdog is True
    assert s.stale_run_rescue_seconds == 90
