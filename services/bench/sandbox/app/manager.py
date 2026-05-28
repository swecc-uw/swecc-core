"""
Sandbox process manager — clones GitHub repos and runs their adapter servers
as subprocesses, proxying traffic through the sandbox's own HTTP server.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import structlog
from bench_common.core.errors import EnvironmentStartupError, ManifestError

try:
    from bench_common.utils.github import InvalidGithubUrl, validate_github_url
except ImportError:  # pragma: no cover - compatibility with older bench_common builds
    from bench_common.utils.github import normalize_github_url

    _GITHUB_URL_RE = re.compile(
        r"^https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
    )

    class InvalidGithubUrl(ValueError):
        pass

    def validate_github_url(url: str) -> str:
        canonical = normalize_github_url(url)
        if not _GITHUB_URL_RE.match(canonical):
            raise InvalidGithubUrl(
                f"Only https://github.com/<owner>/<repo> URLs are accepted; got {url!r}"
            )
        return canonical


log = structlog.get_logger()

ENVS_DIR = Path(os.getenv("ENVS_DIR", "/envs"))
SANDBOX_HOST = os.getenv("SANDBOX_HOST", "localhost")
GIT_CLONE_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_GIT_CLONE_TIMEOUT_SECONDS", "120"))

# Sandbox's own FastAPI listens on 8001; env subprocesses use the pool below.
# Ports are returned to the pool when stop_env() is called, so the counter
# never wraps past 65535 no matter how many envs are cloned over time.
_PORT_RANGE_START = int(os.getenv("SANDBOX_PORT_START", "9000"))
_PORT_RANGE_END = int(os.getenv("SANDBOX_PORT_END", "9999"))
_available_ports: set[int] = set(range(_PORT_RANGE_START, _PORT_RANGE_END + 1))
_registry: dict[str, dict[str, Any]] = {}  # env_id → {process, port, manifest, status}
_lock = asyncio.Lock()


def _resolve_repo_file(base_dir: Path, relative_path: str, label: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ManifestError(f"{label} path must be relative to the manifest directory.")
    root = base_dir.resolve()
    resolved = (base_dir / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestError(f"{label} path must stay inside the manifest directory.") from exc
    if not resolved.is_file():
        raise ManifestError(
            f"{label} {relative_path!r} not found under {base_dir}. "
            f"Check the '{label.lower()}' key in benchanything.json."
        )
    return resolved


async def _terminate_process_tree(
    proc: asyncio.subprocess.Process, *, grace_seconds: float = 5.0
) -> None:
    """Send SIGTERM (then SIGKILL) to the process group, not just the leader.

    Adapters are started with start_new_session=True so they own their own
    process group; killing just the leader leaves forked workers behind as
    zombies. Falls back to direct proc kill if getpgid fails (process already
    gone) or on non-POSIX platforms.
    """
    if proc.returncode is not None:
        return
    pid = proc.pid
    try:
        pgid = os.getpgid(pid)
    except OSError:
        pgid = None
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
    except OSError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        return
    except asyncio.TimeoutError:
        pass
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        log.warning("env_subprocess_unresponsive_after_sigkill", pid=pid)


async def clone_and_start(env_id: str, github_url: str) -> dict[str, Any]:
    """Clone a repo, install its deps, start adapter server, return env URL.

    All failure paths return the port to the pool and rmtree the env_dir
    so a broken submission can't leak ports (eventually exhausting the
    1000-port pool) or disk.
    """
    # Trust-boundary check: reject non-github URLs before invoking git, pip,
    # or running anything from the cloned tree. Anything that reaches the
    # subprocess code below is a github.com/<owner>/<repo> URL.
    try:
        github_url = validate_github_url(github_url)
    except InvalidGithubUrl as exc:
        raise EnvironmentStartupError(str(exc)) from exc

    async with _lock:
        if not _available_ports:
            raise RuntimeError(
                f"No available subprocess ports "
                f"(pool {_PORT_RANGE_START}–{_PORT_RANGE_END} is exhausted). "
                "Stop unused environments first."
            )
        port = min(_available_ports)
        _available_ports.discard(port)

    env_dir = ENVS_DIR / env_id
    proc: asyncio.subprocess.Process | None = None
    stderr_task: asyncio.Task | None = None
    success = False
    try:
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
        try:
            _, stderr = await asyncio.wait_for(
                clone_proc.communicate(),
                timeout=GIT_CLONE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            clone_proc.kill()
            try:
                await asyncio.wait_for(clone_proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                log.warning(
                    "git_clone_unresponsive_after_kill",
                    env_id=env_id,
                    pid=clone_proc.pid,
                )
            log.warning(
                "git_clone_timeout",
                env_id=env_id,
                github_url=github_url,
                timeout_seconds=GIT_CLONE_TIMEOUT_SECONDS,
            )
            raise EnvironmentStartupError(
                f"git clone exceeded {GIT_CLONE_TIMEOUT_SECONDS:.0f}s timeout"
            ) from None
        if clone_proc.returncode != 0:
            log.warning(
                "git_clone_failed",
                env_id=env_id,
                github_url=github_url,
                returncode=clone_proc.returncode,
            )
            raise EnvironmentStartupError(
                f"git clone failed for {github_url!r}:\n{stderr.decode().strip()}"
            )

        # Validate manifest
        from bench_common.env_sdk.manifest import find_manifest_path

        manifest_path = find_manifest_path(env_dir)
        if manifest_path is None:
            raise ManifestError(
                "Repository must contain benchanything.json at its root or under files/. "
                "Copy the template from services/bench/template/ and fill it in."
            )

        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as exc:
            raise ManifestError(f"benchanything.json is not valid JSON: {exc}") from exc

        missing = [k for k in ("adapter", "name", "binding_vow", "scoring") if k not in manifest]
        if missing:
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
            raise ManifestError(f"binding_vow in benchanything.json is invalid: {exc}") from exc

        # Install dependencies — bounded so a hung `pip install` can't pin
        # the port slot forever.
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
            try:
                _, pip_stderr = await asyncio.wait_for(pip_proc.communicate(), timeout=300.0)
            except asyncio.TimeoutError:
                pip_proc.kill()
                # Bounded wait — without this, a pip process stuck in an
                # uninterruptible D-state (slow network mount, NFS hang) would
                # block here forever and starve the outer cleanup of the port
                # we already allocated.
                try:
                    await asyncio.wait_for(pip_proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    log.warning(
                        "pip_proc_unresponsive_after_sigkill",
                        env_id=env_id,
                        pid=pip_proc.pid,
                    )
                raise EnvironmentStartupError(
                    "pip install exceeded 300s timeout — your requirements.txt "
                    "is either too large or one of the listed packages is "
                    "downloading from a slow mirror."
                ) from None
            if pip_proc.returncode != 0:
                raise EnvironmentStartupError(
                    f"pip install failed (exit {pip_proc.returncode}):\n"
                    f"{pip_stderr.decode(errors='replace').strip()[-2000:]}"
                )

        # Start the adapter server
        adapter = manifest.get("adapter", "adapter.py")
        adapter_path = _resolve_repo_file(manifest_path.parent, adapter, "Adapter")

        log.info("starting_env_server", env_id=env_id, port=port)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(adapter_path),
            "--port",
            str(port),
            cwd=str(adapter_path.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Put adapter + any children it spawns into their own process group
            # so we can kill the whole tree on stop_env / failure. Without this
            # an adapter that forks workers leaves zombies after proc.kill().
            start_new_session=True,
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

        async with httpx.AsyncClient(timeout=2.0) as client:
            for _ in range(30):
                await asyncio.sleep(1.0)
                try:
                    r = await client.get(local_health_url)
                    if r.status_code == 200:
                        _registry[env_id]["status"] = "running"
                        log.info("env_server_ready", env_id=env_id, url=env_url)
                        success = True
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
        if stderr_task is not None:
            stderr_task.cancel()
        if not success:
            # Tear down everything we allocated: kill the subprocess (whole
            # process group, see _terminate_process_tree), return the port to
            # the pool, drop the registry entry, rmtree the dir. Without this,
            # broken submissions leak ports and disk forever.
            if proc is not None:
                await _terminate_process_tree(proc, grace_seconds=2.0)
            _registry.pop(env_id, None)
            _available_ports.add(port)
            shutil.rmtree(env_dir, ignore_errors=True)


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
    await _terminate_process_tree(proc, grace_seconds=5.0)
    # Return the port to the pool so it can be reused by future clones.
    port = entry.get("port")
    if port is not None:
        _available_ports.add(port)
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
