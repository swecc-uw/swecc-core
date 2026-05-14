"""
HTTP adapter — wraps your env in the BenchAnything HTTP protocol.
You don't need to edit this file. Just make sure --port is accepted (it is).

Local dev:
    python adapter.py            # starts on port 8765
    python adapter.py --port 9000

The platform sandbox will start this automatically and assign its own port.
"""
import argparse
import sys
import os

# When running locally outside the sandbox, make the SDK importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from template.env import MyEnv       # <- change this if you rename env.py / class
from bench_common.env_sdk import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    print(f"MyEnv adapter → http://{args.host}:{args.port}")
    print("  GET  /health")
    print("  POST /reset   POST /step   POST /close")
    serve(MyEnv, host=args.host, port=args.port)
