"""
HTTP adapter — wraps your env in the BenchAnything HTTP protocol.
You don't need to edit this file. Just make sure --port is accepted (it is).

Local dev:
    python adapter.py            # starts on port 8765
    python adapter.py --port 9000
    python adapter.py --max-steps 10

The platform sandbox will start this automatically and assign its own port.
"""

import argparse
import os
import sys

# When running locally outside the sandbox, make the SDK importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bench_common.env_sdk import serve
from template.env import MyEnv  # <- change this if you rename env.py / class


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
    print("  GET  /health")
    print("  POST /reset   POST /step   POST /close")
    if max_steps is not None:
        print(f"  max_steps={max_steps}")
    serve(MyEnv, host=args.host, port=args.port, max_steps=max_steps)
