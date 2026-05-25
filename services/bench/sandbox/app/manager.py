"""
Sandbox process manager — clones GitHub repos and runs their adapter servers
as subprocesses, proxying traffic through the sandbox's own HTTP server.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import structlog
from bench_common.core.errors import EnvironmentStartupError, ManifestError

log = structlog.get_logger()

ENVS_DIR = Path(os.getenv("ENVS_DIR", "/envs"))
SANDBOX_HOST = os.getenv("SANDBOX_HOST", "localhost")

# Sandbox's own FastAPI listens on 8001; env subprocesses start from 9000
_port_counter = 9000
_registry: dict[str, dict[str, Any]] = {}  # env_id → {process, port, manifest, status}
_lock = asyncio.Lock()


async def clone_and_start(env_id: str, github_url: str) -> dict[str, Any]:
    """Clone a repo, install its deps, start adapter server, return env URL."""
    global _port_counter

    async with _lock:
        port = _port_counter
        _port_counter += 1

    env_dir = ENVS_DIR / env_id

    # Clean up any stale clone
    if env_dir.exists():
        shutil.rmtree(env_dir)

    log.info("cloning_repo", env_id=env_id, github_url=github_url)
    clone_proc = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth=1",
        github_url,
        str(env_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await clone_proc.communicate()
    if clone_proc.returncode != 0:
        raise EnvironmentStartupError(
            f"git clone failed for {github_url!r}:\n{stderr.decode().strip()}"
        )

    # Validate manifest
    manifest_path = env_dir / "benchanything.json"
    if not manifest_path.exists():
        shutil.rmtree(env_dir, ignore_errors=True)
        raise ManifestError(
            "Repository must contain a benchanything.json at its root. "
            "Copy the template from services/bench/template/ and fill it in."
        )

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        shutil.rmtree(env_dir, ignore_errors=True)
        raise ManifestError(f"benchanything.json is not valid JSON: {exc}") from exc

    missing = [k for k in ("adapter", "name", "binding_vow", "scoring") if k not in manifest]
    if missing:
        shutil.rmtree(env_dir, ignore_errors=True)
        raise ManifestError(
            f"benchanything.json is missing required key(s): "
            f"{', '.join(repr(k) for k in missing)}"
        )

    # Validate the binding vow schema before spinning up a subprocess
    try:
        from bench_common.core.binding_vow import BindingVow

        vow_raw = {**manifest["binding_vow"], "id": "validate", "domain_id": "validate"}
        BindingVow.model_validate(vow_raw).validate()
    except Exception as exc:
        shutil.rmtree(env_dir, ignore_errors=True)
        raise ManifestError(f"binding_vow in benchanything.json is invalid: {exc}") from exc

    # Install dependencies
    req_file = env_dir / "requirements.txt"
    if req_file.exists():
        log.info("installing_deps", env_id=env_id)
        pip_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "-r",
            str(req_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await pip_proc.communicate()

    # Start the adapter server
    adapter = manifest.get("adapter", "adapter.py")
    adapter_path = env_dir / adapter
    if not adapter_path.exists():
        raise ManifestError(
            f"Adapter {adapter!r} not found in repository root. "
            f"Check the 'adapter' key in benchanything.json."
        )

    log.info("starting_env_server", env_id=env_id, port=port)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(adapter_path),
        "--port",
        str(port),
        cwd=str(env_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _registry[env_id] = {
        "process": proc,
        "port": port,
        "manifest": manifest,
        "status": "starting",
        "stderr_lines": [],
    }

    # Wait for health check (up to 30 seconds), collecting stderr in background
    env_url = f"http://{SANDBOX_HOST}:{port}"
    local_health_url = f"http://localhost:{port}/health"

    async def _collect_stderr() -> None:
        assert proc.stderr is not None
        async for line in proc.stderr:
            decoded = line.decode(errors="replace").rstrip()
            _registry[env_id]["stderr_lines"].append(decoded)
            log.debug("adapter_stderr", env_id=env_id, line=decoded)

    stderr_task = asyncio.create_task(_collect_stderr())

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            for _ in range(30):
                await asyncio.sleep(1.0)
                try:
                    r = await client.get(local_health_url)
                    if r.status_code == 200:
                        _registry[env_id]["status"] = "running"
                        log.info("env_server_ready", env_id=env_id, url=env_url)
                        return {"env_id": env_id, "url": env_url, "manifest": manifest}
                except httpx.TransportError:
                    pass
                # Bail early if process died — include stderr so student sees their traceback
                if proc.returncode is not None:
                    await asyncio.sleep(0.2)  # let stderr_task flush
                    stderr_tail = _format_stderr(_registry[env_id]["stderr_lines"])
                    raise EnvironmentStartupError(
                        f"Adapter exited with code {proc.returncode} before "
                        f"GET /health responded.\n{stderr_tail}"
                    )

        await asyncio.sleep(0.2)
        stderr_tail = _format_stderr(_registry[env_id]["stderr_lines"])
        _registry[env_id]["status"] = "unhealthy"
        raise EnvironmentStartupError(
            f"Adapter did not respond to GET /health within 30 s.\n"
            f"Make sure your adapter calls serve() and accepts --port.\n"
            f"{stderr_tail}"
        )
    finally:
        stderr_task.cancel()


def _format_stderr(lines: list[str], tail: int = 20) -> str:
    if not lines:
        return "(no stderr output captured)"
    shown = lines[-tail:]
    prefix = f"--- adapter stderr (last {len(shown)} lines) ---\n"
    return prefix + "\n".join(shown)


async def stop_env(env_id: str) -> None:
    entry = _registry.pop(env_id, None)
    if entry is None:
        return
    proc: asyncio.subprocess.Process = entry["process"]
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
    env_dir = ENVS_DIR / env_id
    shutil.rmtree(env_dir, ignore_errors=True)
    log.info("env_stopped", env_id=env_id)


def get_env_port(env_id: str) -> int | None:
    entry = _registry.get(env_id)
    return entry["port"] if entry else None


def get_manifest(env_id: str) -> dict[str, Any] | None:
    entry = _registry.get(env_id)
    return entry["manifest"] if entry else None


def get_status(env_id: str) -> dict[str, Any] | None:
    entry = _registry.get(env_id)
    if entry is None:
        return None
    return {
        "env_id": env_id,
        "port": entry["port"],
        "status": entry["status"],
        "url": f"http://{SANDBOX_HOST}:{entry['port']}",
        "stderr_tail": _format_stderr(entry.get("stderr_lines", [])),
    }
