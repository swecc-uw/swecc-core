"""
Register SimpleTriviaEnv with the platform.

Run this once (and again any time you change domain.py).
The adapter server does NOT need to be running for registration.

Usage:
    uv run python docs/examples/simple_trivia/register.py
    uv run python docs/examples/simple_trivia/register.py --api http://prod-api:8000
    uv run python docs/examples/simple_trivia/register.py --publish
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from bench_common.env_sdk.registration import publish_domain, register_domain
from docs.examples.simple_trivia.domain import DOMAIN_CONFIG, DOMAIN_ID

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register SimpleTriviaEnv")
    parser.add_argument("--api", default="http://localhost:8000", help="Platform API URL")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also publish (freeze Binding Vow, enable leaderboard)",
    )
    args = parser.parse_args()

    register_domain(DOMAIN_CONFIG, api_url=args.api)

    if args.publish:
        publish_domain(DOMAIN_ID, api_url=args.api)
