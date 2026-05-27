"""
Generic domain registration CLI.

Dynamically loads a domain.py file and registers its DOMAIN_CONFIG with the
platform API.  Env developers no longer need a per-env register.py script.

Usage:
    # Register from a domain.py that exports DOMAIN_CONFIG
    uv run python -m src.env_sdk.register path/to/domain.py

    # Auto-derive domain ID from the parent folder name
    uv run python -m src.env_sdk.register path/to/my_env/domain.py --auto-id

    # Override the domain ID explicitly
    uv run python -m src.env_sdk.register path/to/domain.py --id my-custom-id

    # Also publish after registering
    uv run python -m src.env_sdk.register path/to/domain.py --publish

    # Point at a different API server
    uv run python -m src.env_sdk.register path/to/domain.py --api http://prod:8000
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from bench_common.env_sdk.registration import DomainConfig, publish_domain, register_domain


def _load_domain_config(path: str) -> DomainConfig:
    """
    Import a domain.py file and return its DOMAIN_CONFIG.

    Looks for a module-level variable named DOMAIN_CONFIG (a DomainConfig
    instance).  If not found, raises a clear error.
    """
    filepath = Path(path).resolve()
    if not filepath.exists():
        raise FileNotFoundError(f"Domain file not found: {filepath}")
    if not filepath.suffix == ".py":
        raise ValueError(f"Expected a .py file, got: {filepath}")

    # Add parent dir to sys.path so relative imports within domain.py work
    parent = str(filepath.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    spec = importlib.util.spec_from_file_location("_domain_module", filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {filepath}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = getattr(module, "DOMAIN_CONFIG", None)
    if config is None:
        raise AttributeError(
            f"{filepath} does not export a 'DOMAIN_CONFIG' variable.\n"
            f"Your domain.py must define:\n"
            f"  DOMAIN_CONFIG = DomainConfig(id=..., name=..., ...)"
        )
    if not isinstance(config, DomainConfig):
        raise TypeError(
            f"DOMAIN_CONFIG in {filepath} is {type(config).__name__}, " f"expected DomainConfig"
        )
    return config


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m bench_common.env_sdk.register",
        description="Register any domain.py with the BenchAnything platform.",
    )
    parser.add_argument(
        "domain_file",
        help="Path to a domain.py file that exports DOMAIN_CONFIG",
    )
    parser.add_argument(
        "--api",
        default=None,
        help="bench-api URL (default: https://api.swecc.org/bench, or local with MESOCOSM_LOCAL=1)",
    )
    parser.add_argument(
        "--id",
        dest="domain_id",
        default=None,
        help="Override the domain ID (default: use DOMAIN_CONFIG.id)",
    )
    parser.add_argument(
        "--auto-id",
        action="store_true",
        help="Derive domain ID from the parent folder name of domain.py",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also publish (freeze Binding Vow, enable leaderboard)",
    )
    args = parser.parse_args()

    config = _load_domain_config(args.domain_file)

    # Apply ID overrides
    if args.auto_id:
        folder_name = Path(args.domain_file).resolve().parent.name
        config = config.model_copy(
            update={
                "id": folder_name,
                "binding_vow": config.binding_vow.model_copy(
                    update={
                        "id": f"{folder_name}-v{config.binding_vow.version}",
                        "domain_id": folder_name,
                    }
                ),
            }
        )
    elif args.domain_id:
        config = config.model_copy(
            update={
                "id": args.domain_id,
                "binding_vow": config.binding_vow.model_copy(
                    update={
                        "id": f"{args.domain_id}-v{config.binding_vow.version}",
                        "domain_id": args.domain_id,
                    }
                ),
            }
        )

    register_domain(config, api_url=args.api)

    if args.publish:
        publish_domain(config.id, api_url=args.api)


if __name__ == "__main__":
    main()
