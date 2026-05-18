"""Register with platform API (httpx; no MCP)."""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from bench_common.env_sdk.registration import publish_domain, register_domain
from docs.examples.game_2048.domain import DOMAIN_CONFIG, DOMAIN_ID

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    register_domain(DOMAIN_CONFIG, api_url=a.api)
    if a.publish:
        publish_domain(DOMAIN_ID, api_url=a.api)
