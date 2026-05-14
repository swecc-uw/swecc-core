"""
BenchAnything env_sdk
======================
Optional utilities — you do NOT need these to publish an environment.

The platform's only requirement is that your environment exposes these HTTP
endpoints (Section 5.2 of the design doc):

    GET  /health
    POST /reset   { "episode_id": "...", "seed": 42 }       → Observation JSON
    POST /step    { "episode_id": "...", "action": ... }     → StepResult JSON
    POST /close   { "episode_id": "..." }                   → {}

Implement those however you like (FastAPI, Flask, Express, your own HTTP server).

This module exists for a single use-case: you already have a 3rd-party env
(e.g. a Gymnasium env) and want to wrap it without writing the HTTP boilerplate
yourself.  Import BaseEnv + serve() for that case only.

    from bench_common.env_sdk import BaseEnv, StepResult, serve  # adapter path
    from bench_common.env_sdk.registration import register_domain, DomainConfig  # all paths
"""
from bench_common.env_sdk.base import BaseEnv, StepResult
from bench_common.env_sdk.server import serve
from bench_common.env_sdk.registration import register_domain, DomainConfig

__all__ = ["BaseEnv", "StepResult", "serve", "register_domain", "DomainConfig"]
