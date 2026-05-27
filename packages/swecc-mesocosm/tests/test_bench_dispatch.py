"""Routing of env-author argv to bench_common."""

from swecc_mesocosm.bench_dispatch import try_dispatch_bench


def test_dispatch_init(monkeypatch) -> None:
    called: list[list[str] | None] = []

    def fake_main(argv: list[str] | None) -> None:
        called.append(argv)

    monkeypatch.setattr("bench_common.cli.main.main", fake_main)
    assert try_dispatch_bench(["init"]) is True
    assert called == [["init"]]


def test_dispatch_run_local(monkeypatch) -> None:
    called: list[list[str] | None] = []

    def fake_main(argv: list[str] | None) -> None:
        called.append(argv)

    monkeypatch.setattr("bench_common.cli.main.main", fake_main)
    assert try_dispatch_bench(["run", "local", "--model", "ollama/llama3.2"]) is True
    assert called[0][0:2] == ["run", "local"]


def test_run_get_not_dispatched() -> None:
    assert try_dispatch_bench(["run", "get", "run-1"]) is False


def test_dispatch_register_domain_py(monkeypatch, tmp_path) -> None:
    domain_file = tmp_path / "domain.py"
    domain_file.write_text("DOMAIN_CONFIG = None\n", encoding="utf-8")
    called: list[list[str] | None] = []

    def fake_main(argv: list[str] | None) -> None:
        called.append(argv)

    monkeypatch.setattr("bench_common.cli.main.main", fake_main)
    assert try_dispatch_bench(["register", str(domain_file), "--publish"]) is True
    assert called == [["register", str(domain_file), "--publish"]]


def test_register_flags_not_dispatched_to_bench() -> None:
    """API register removed; only domain.py paths dispatch to bench_common."""
    assert try_dispatch_bench(["register", "--id", "my-bench"]) is False
