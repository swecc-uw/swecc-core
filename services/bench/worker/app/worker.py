"""
EC2 Bench Worker — polls the BenchAnything API for queued full-bench jobs,
clones the env repo, runs all five canonical models against it, and reports
results back.

Required environment variables:
    WORKER_API_URL        Public URL of the BenchAnything API
    ANTHROPIC_API_KEY     (and other model provider keys as needed)

Optional environment variables:
    WORKER_POLL_INTERVAL  Seconds between API polls (default: 10)
    WORKER_EPISODES_PER_MODEL  Episodes per model per job (default: 5)
    WORKER_RUN_POLL_TIMEOUT    Max seconds to wait for a run to complete (default: 300)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from subprocess import PIPE
from subprocess import run as subprocess_run
from typing import Any

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
log = logging.getLogger("bench_worker")

POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "10"))
API_URL = os.environ["WORKER_API_URL"].rstrip("/")
SUPPORTED_MODELS = [
    "anthropic/claude-sonnet-4-6",
    "openai/gpt-4o",
    "gemini/gemini-2.5-flash",
    "deepseek/deepseek-chat",
    "xai/grok-2",
]
EPISODES_PER_MODEL = int(os.getenv("WORKER_EPISODES_PER_MODEL", "5"))
RUN_POLL_TIMEOUT = int(os.getenv("WORKER_RUN_POLL_TIMEOUT", "300"))

_django_ready = False


def _ensure_django() -> None:
    """Bootstrap Django ORM against shared Postgres (DB_* from server_env)."""
    global _django_ready
    if _django_ready:
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
    import django

    django.setup()
    _django_ready = True


def poll_and_process() -> None:
    resp = requests.get(f"{API_URL}/v1/bench/jobs", params={"status": "queued"}, timeout=10)
    resp.raise_for_status()
    jobs = resp.json()
    if not jobs:
        return

    job = jobs[0]
    job_id = job["id"]
    log.info(f"claiming job {job_id} (env={job['env_id']})")

    claim_resp = requests.patch(f"{API_URL}/v1/bench/jobs/{job_id}/claim", timeout=10)
    if claim_resp.status_code == 409:
        log.info(f"job {job_id} already claimed — skipping")
        return
    claim_resp.raise_for_status()

    log.info(f"running full bench for job {job_id}")
    try:
        model_results = asyncio.run(run_full_bench(job))
        requests.patch(
            f"{API_URL}/v1/bench/jobs/{job_id}/complete",
            json={"model_results": model_results, "failed": False},
            timeout=30,
        )
        log.info(f"job {job_id} completed — scores: {_score_summary(model_results)}")
    except Exception:
        log.exception(f"job {job_id} failed")
        requests.patch(
            f"{API_URL}/v1/bench/jobs/{job_id}/complete",
            json={"model_results": {}, "failed": True},
            timeout=30,
        )


async def run_full_bench(job: dict[str, Any]) -> dict[str, Any]:
    """Clone the env repo, start the adapter, bench all models, return scores."""
    github_url = job["github_url"]
    domain_id = job.get("domain_id")

    work_dir = Path(tempfile.mkdtemp(prefix=f"bench_{job['id']}_"))
    log.info(f"working in {work_dir}")
    try:
        repo_dir = await _clone_repo(github_url, work_dir)
        manifest = _read_manifest(repo_dir)
        await _install_deps(repo_dir)

        port = _find_free_port()
        proc = await _start_adapter(repo_dir, manifest, port)
        env_url = f"http://localhost:{port}"
        try:
            await _wait_for_health(env_url)
            return await _bench_all_models(domain_id, manifest, env_url)
        finally:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def _clone_repo(github_url: str, work_dir: Path) -> Path:
    repo_dir = work_dir / "repo"
    log.info(f"cloning {github_url}")
    result = subprocess_run(
        ["git", "clone", "--depth=1", github_url, str(repo_dir)],
        stdout=PIPE,
        stderr=PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed for {github_url!r}:\n{result.stderr.decode().strip()}"
        )
    return repo_dir


def _read_manifest(repo_dir: Path) -> dict[str, Any]:
    manifest_path = repo_dir / "benchanything.json"
    if not manifest_path.exists():
        raise RuntimeError(
            "Repository has no benchanything.json at its root. "
            "See the environment authoring guide for the required format."
        )
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"benchanything.json is not valid JSON: {exc}") from exc

    for key in ("adapter", "name", "binding_vow", "scoring"):
        if key not in manifest:
            raise RuntimeError(f"benchanything.json is missing required key: {key!r}")
    return manifest


async def _install_deps(repo_dir: Path) -> None:
    req_file = repo_dir / "requirements.txt"
    if not req_file.exists():
        return
    log.info("installing env dependencies")
    proc = await asyncio.create_subprocess_exec(
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
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pip install failed:\n{stderr.decode().strip()}")


async def _start_adapter(
    repo_dir: Path, manifest: dict[str, Any], port: int
) -> asyncio.subprocess.Process:
    adapter = manifest.get("adapter", "adapter.py")
    adapter_path = repo_dir / adapter
    if not adapter_path.exists():
        raise RuntimeError(
            f"Adapter {adapter!r} not found in repository root. "
            f"Check the 'adapter' key in benchanything.json."
        )
    log.info(f"starting adapter on port {port}")
    return await asyncio.create_subprocess_exec(
        sys.executable,
        str(adapter_path),
        "--port",
        str(port),
        cwd=str(repo_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _wait_for_health(url: str, timeout: int = 30) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=2.0) as client:
        for attempt in range(timeout):
            await asyncio.sleep(1.0)
            try:
                r = await client.get(f"{url}/health")
                if r.status_code == 200:
                    log.info(f"adapter healthy at {url} after {attempt + 1}s")
                    return
            except httpx.TransportError:
                pass
    raise RuntimeError(
        f"Adapter at {url} did not respond to GET /health within {timeout}s. "
        f"Make sure your adapter calls serve() and accepts --port."
    )


async def _bench_all_models(
    domain_id: str | None,
    manifest: dict[str, Any],
    env_url: str,
) -> dict[str, Any]:
    """Register the domain locally and run each canonical model."""
    _ensure_django()
    from bench_common.core.binding_vow import BindingVow
    from bench_common.core.domain import Domain, EnvironmentEndpoint
    from bench_common.core.scoring import ScoringConfig
    from bench_common.inference.bench import bench
    from bench_common.storage import database as db

    await db.init_db()

    # Build and persist a local domain record from the manifest so bench() can
    # look it up.  The domain_id comes from the API's record if available;
    # otherwise we generate one for this worker's local Postgres record.
    import uuid

    local_domain_id = domain_id or str(uuid.uuid4())
    vow_raw: dict[str, Any] = {
        **manifest["binding_vow"],
        "id": f"{local_domain_id}-vow",
        "domain_id": local_domain_id,
    }
    try:
        vow = BindingVow.model_validate(vow_raw)
        vow.validate()
    except Exception as exc:
        raise RuntimeError(f"Invalid binding_vow in manifest: {exc}") from exc

    scoring = ScoringConfig.model_validate(manifest["scoring"])
    domain = Domain(
        id=local_domain_id,
        name=manifest.get("name", "worker-env"),
        owner_id="worker",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url=env_url),
        scoring=scoring,
        status="draft",
    )
    await db.save_domain(domain)

    model_results: dict[str, Any] = {}
    for model in SUPPORTED_MODELS:
        log.info(f"benching model={model} episodes={EPISODES_PER_MODEL}")
        try:
            result = await bench(
                model=model,
                domain_id=local_domain_id,
                env_url=env_url,
                num_episodes=EPISODES_PER_MODEL,
                quiet=True,
            )
            primary_metric = domain.scoring.primary_metric
            model_results[model] = {
                "status": "completed",
                "primary_score": result.scores.get(primary_metric),
                "scores": result.scores,
                "completed_episodes": result.completed,
                "failed_episodes": result.failed,
            }
            log.info(f"model={model} primary_score={result.scores.get(primary_metric)}")
        except Exception as exc:
            log.exception(f"model={model} failed: {exc}")
            model_results[model] = {
                "status": "failed",
                "primary_score": None,
                "error": str(exc),
            }

    return model_results


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _score_summary(model_results: dict[str, Any]) -> str:
    return ", ".join(
        f"{m.split('/')[-1]}={r.get('primary_score')}" for m, r in model_results.items()
    )


def _wait_for_api(max_attempts: int = 60, delay: float = 5.0) -> None:
    """Block until the API responds.  Prevents crashes on cold-start DNS races."""
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(f"{API_URL}/v1/bench/jobs", params={"status": "queued"}, timeout=3)
            if resp.status_code < 500:
                log.info(f"API reachable at {API_URL} after {attempt} attempt(s)")
                return
        except requests.RequestException as exc:
            log.info(f"waiting for API ({attempt}/{max_attempts}): {exc}")
        time.sleep(delay)
    raise RuntimeError(f"API at {API_URL} never became reachable after {max_attempts} attempts")


def main() -> None:
    _wait_for_api()
    log.info(f"polling {API_URL} every {POLL_INTERVAL}s")
    while True:
        try:
            poll_and_process()
        except Exception:
            log.exception("poll cycle failed — retrying after sleep")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
