from __future__ import annotations

from typing import Any

from swecc_mesocosm.infer import build_domain_payload, suggest_benchmark_shape, sync_binding_vow_to_domain_id


def test_sync_binding_vow_to_domain_id() -> None:
    shape = suggest_benchmark_shape("trivia quiz")
    body: dict[str, Any] = build_domain_payload(
        benchmark_id="original",
        name="X",
        owner_id="o",
        description="trivia",
        env_url="http://example.com",
        shape=shape,
    )
    body["id"] = "overridden"
    sync_binding_vow_to_domain_id(body)
    assert body["binding_vow"]["domain_id"] == "overridden"
    assert body["binding_vow"]["id"] == "overridden-vow-1"
