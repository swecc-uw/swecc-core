"""
Start the HTTP adapter server for WordleEnv.

Run this in one terminal while the platform API is running in another.
The platform agent runtime will call /reset and /step on this server.

Usage:
    uv run python docs/examples/wordle/adapter.py
    uv run python docs/examples/wordle/adapter.py --port 9000
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from docs.examples.wordle.env import WordleEnv
from bench_common.env_sdk import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WordleEnv adapter server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    print(f"Starting WordleEnv adapter on http://{args.host}:{args.port}")
    print(f"Health check: http://localhost:{args.port}/health")
    print("Press Ctrl+C to stop.\n")

    serve(WordleEnv, host=args.host, port=args.port)
