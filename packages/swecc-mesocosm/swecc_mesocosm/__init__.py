"""swecc-mesocosm — CLI and Python client for SWECC's bench platform."""

from importlib.metadata import PackageNotFoundError, version

from swecc_mesocosm.client import BenchClient

try:
    __version__ = version("swecc-mesocosm")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = ["BenchClient", "__version__"]
