"""
Start the HTTP adapter server for SimpleTriviaEnv.

Run this in one terminal while the platform API is running in another.
The platform agent runtime will call /reset and /step on this server.

Usage:
    uv run python docs/examples/simple_trivia/adapter.py
    uv run python docs/examples/simple_trivia/adapter.py --port 9000
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from docs.examples.simple_trivia.env import SimpleTriviaEnv
from bench_common.env_sdk import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SimpleTriviaEnv adapter server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    print(f"Starting SimpleTriviaEnv adapter on http://{args.host}:{args.port}")
    print("Health check: http://localhost:8765/health")
    print("Press Ctrl+C to stop.\n")

    serve(SimpleTriviaEnv, host=args.host, port=args.port)
