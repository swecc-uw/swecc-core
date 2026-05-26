"""Tests for benchanything.json → DomainConfig loading."""

from pathlib import Path

import pytest
from bench_common.core.errors import ManifestError
from bench_common.env_sdk.manifest import domain_config_from_manifest, load_manifest

_TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "bench_common"
    / "cli"
    / "templates"
    / "benchanything.json"
)


def test_load_manifest_template() -> None:
    manifest = load_manifest(_TEMPLATE)
    assert manifest["name"] == "My Environment"
    assert "binding_vow" in manifest


def test_domain_config_from_manifest() -> None:
    cfg = domain_config_from_manifest(_TEMPLATE, env_url="http://localhost:9999")
    assert cfg.id == "my-env"
    assert cfg.endpoint.url == "http://localhost:9999"
    assert cfg.binding_vow.version == "1.0.0"
    cfg.binding_vow.validate()


def test_domain_config_derives_id_from_folder(tmp_path: Path) -> None:
    manifest = tmp_path / "benchanything.json"
    data = load_manifest(_TEMPLATE)
    data.pop("id", None)
    manifest.write_text(
        __import__("json").dumps(data),
        encoding="utf-8",
    )
    cfg = domain_config_from_manifest(manifest)
    assert cfg.id == tmp_path.name


def test_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "nope.json")
