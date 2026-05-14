"""
HTTP adapter for Game2048Env.

  uv run python docs/examples/game_2048/adapter.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from bench_common.env_sdk import serve
from docs.examples.game_2048.env import Game2048Env

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Game2048Env adapter server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    print(f"Starting Game2048Env on http://{args.host}:{args.port}")
    serve(Game2048Env, host=args.host, port=args.port)
