import os

from bench_common.config import Settings


def test_mq_enabled_disables_orphan_reaper(monkeypatch):
    monkeypatch.setenv("ORCH_MQ_ENABLED", "1")
    s = Settings()
    assert s.mq_enabled is True
    assert s.enable_orphan_reaper is False


def test_bench_mq_prefetch_override(monkeypatch):
    monkeypatch.delenv("ORCH_MQ_ENABLED", raising=False)
    monkeypatch.setenv("BENCH_MQ_PREFETCH", "5")
    s = Settings()
    assert s.mq_prefetch == 5
