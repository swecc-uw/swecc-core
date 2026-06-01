"""
HTTP adapter — exposes your env via the BenchAnything four-endpoint protocol.

Local dev:
    python adapter.py
    python adapter.py --port 9000
    python adapter.py --max-steps 10
"""

import argparse
import os

from bench_common.env_sdk import serve
from env import MyEnv


def _resolve_max_steps(cli_value: int | None) -> int | None:
    if cli_value is not None:
        return cli_value
    raw = os.environ.get("BENCH_ADAPTER_MAX_STEPS", "").strip()
    return int(raw) if raw else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Hard cap on env steps per episode (default: BENCH_ADAPTER_MAX_STEPS env)",
    )
    args = parser.parse_args()

    max_steps = _resolve_max_steps(args.max_steps)
    print(f"MyEnv adapter → http://{args.host}:{args.port}")
    if max_steps is not None:
        print(f"  max_steps={max_steps}")
    serve(MyEnv, host=args.host, port=args.port, max_steps=max_steps)
