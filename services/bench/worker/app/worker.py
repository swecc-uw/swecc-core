"""
EC2 Bench Worker — polls the BenchAnything API for queued full-bench jobs
and executes them locally, cloning the env repo fresh for each run.

Usage on the EC2 instance:
    WORKER_API_URL=https://api.benchanything.com python -m src.worker.bench_worker

Required environment variables:
    WORKER_API_URL        Public URL of the BenchAnything API
    ANTHROPIC_API_KEY     (and other model provider keys)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from subprocess import PIPE, run
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
    "google/gemini-2.0-flash",
    "deepseek/deepseek-chat",
    "xai/grok-2",
]
EPISODES_PER_MODEL = int(os.getenv("WORKER_EPISODES_PER_MODEL", "5"))
RUN_POLL_TIMEOUT = int(os.getenv("WORKER_RUN_POLL_TIMEOUT", "300"))  # seconds


def poll_and_process():
    resp = requests.get(f"{API_URL}/v1/bench/jobs", params={"status": "queued"})
    resp.raise_for_status()
    jobs = resp.json()
    if not jobs:
        return

    job = jobs[0]
    job_id = job["id"]
    log.info(f"claiming job {job_id} for env {job['env_id']}")

    claim_resp = requests.patch(f"{API_URL}/v1/bench/jobs/{job_id}/claim")
    if claim_resp.status_code == 409:
        log.info(f"job {job_id} already claimed, skipping")
        return
    claim_resp.raise_for_status()

    log.info(f"running full bench for job {job_id}")
    try:
        model_results = run_full_bench(job)
        requests.patch(
            f"{API_URL}/v1/bench/jobs/{job_id}/complete",
            json={"model_results": model_results, "failed": False},
        )
        log.info(f"job {job_id} completed")
    except Exception as exc:
        log.exception(f"job {job_id} failed: {exc}")
        requests.patch(
            f"{API_URL}/v1/bench/jobs/{job_id}/complete",
            json={"model_results": {}, "failed": True},
        )


def run_full_bench(job):
    github_url = job["github_url"]
    domain_id = job.get("domain_id")

    # Clone repo fresh into a temp directory
    work_dir = Path(tempfile.mkdtemp(prefix=f"bench_{job['id']}_"))
    log.info(f"cloning {github_url} into {work_dir}")
    try:
        proc = run(
            ["git", "clone", "--depth=1", github_url, str(work_dir / "repo")],
            stdout=PIPE,
            stderr=PIPE,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {proc.stderr.decode().strip()}")

        repo_dir = work_dir / "repo"
        manifest_path = repo_dir / "benchanything.json"
        if not manifest_path.exists():
            raise RuntimeError("No benchanything.json found")

        # Additional processing logic here
        return {}
    finally:
        shutil.rmtree(work_dir)


async def _wait_for_health(url: str, timeout: int = 30) -> None:
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(timeout):
            await asyncio.sleep(1.0)
            try:
                r = await client.get(f"{url}/health")
                if r.status_code == 200:
                    return
            except httpx.TransportError:
                pass
    raise RuntimeError(f"Server at {url} did not become healthy within {timeout}s")


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_api(max_attempts: int = 60, delay: float = 5.0) -> None:
    """Block until API_URL responds. Avoids crashing on cold-start DNS races."""
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(f"{API_URL}/v1/bench/jobs", params={"status": "queued"}, timeout=3)
            if resp.status_code < 500:
                log.info(f"API reachable at {API_URL} after {attempt} attempt(s)")
                return
            log.info(
                f"API at {API_URL} returned {resp.status_code} (attempt {attempt}/{max_attempts})"
            )
        except requests.RequestException as exc:
            log.info(f"waiting for API at {API_URL} (attempt {attempt}/{max_attempts}): {exc}")
        time.sleep(delay)
    raise RuntimeError(f"API at {API_URL} never became reachable after {max_attempts} attempts")


def main():
    _wait_for_api()
    while True:
        try:
            poll_and_process()
        except Exception:
            log.exception("poll cycle failed; will retry after sleep")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
