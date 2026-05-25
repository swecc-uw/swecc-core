from __future__ import annotations

from typing import Any, cast

import httpx

from swecc_mesocosm.settings import settings


def _json_dict(data: Any) -> dict[str, Any]:
    return cast(dict[str, Any], data)


def _json_list_dict(data: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], data)


class BenchClient:
    """Async HTTP client for bench-api (`/v1/...`)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or settings.base_url).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=httpx.Timeout(settings.request_timeout_s),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_domains(
        self, *, published_only: bool | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if published_only is True:
            params["published"] = "true"
        r = await self._client.get("v1/domains", params=params or None)
        r.raise_for_status()
        return _json_list_dict(r.json())

    async def get_domain(self, domain_id: str) -> dict[str, Any]:
        r = await self._client.get(f"v1/domains/{domain_id}")
        r.raise_for_status()
        return _json_dict(r.json())

    async def create_domain(self, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.post("v1/domains", json=body)
        r.raise_for_status()
        return _json_dict(r.json())

    async def upsert_domain(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST a new domain, or on 409 Conflict PATCH the existing draft."""
        r = await self._client.post("v1/domains", json=body)
        if r.status_code == 201:
            return _json_dict(r.json())
        if r.status_code != 409:
            r.raise_for_status()
        domain_id = body.get("id")
        if not domain_id:
            r.raise_for_status()
        patch: dict[str, Any] = {
            k: body[k]
            for k in (
                "name",
                "binding_vow",
                "endpoint",
                "scoring",
                "tags",
                "detail",
                "pricing",
                "version_history",
                "image_url",
                "profile_picture_url",
                "has_gold_benchmark",
            )
            if k in body
        }
        p = await self._client.patch(f"v1/domains/{domain_id}", json=patch)
        p.raise_for_status()
        return _json_dict(p.json())

    async def publish_domain(self, domain_id: str) -> dict[str, Any]:
        r = await self._client.post(f"v1/domains/{domain_id}/publish")
        r.raise_for_status()
        return _json_dict(r.json())

    async def test_episode(self, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.post("v1/test/episode", json=body)
        r.raise_for_status()
        return _json_dict(r.json())

    async def create_run(self, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.post("v1/runs", json=body)
        r.raise_for_status()
        return _json_dict(r.json())

    async def get_run(self, run_id: str) -> dict[str, Any]:
        r = await self._client.get(f"v1/runs/{run_id}")
        r.raise_for_status()
        return _json_dict(r.json())

    async def list_episodes(self, run_id: str) -> list[dict[str, Any]]:
        r = await self._client.get(f"v1/runs/{run_id}/episodes")
        r.raise_for_status()
        return _json_list_dict(r.json())

    async def get_run_traces(self, run_id: str) -> dict[str, Any]:
        r = await self._client.get(f"v1/runs/{run_id}/traces")
        r.raise_for_status()
        return _json_dict(r.json())
