"""
Pytest configuration for bench-api tests.

Environment variables and the SQLite database override are applied before any
test module imports app.main (see ai/tests/conftest.py). Database setup follows
services/server/run_tests.py via test_support.django_setup.
"""

from test_support.conftest_helpers import ensure_bench_root_on_path
from test_support.django_setup import configure_django_for_tests
from test_support.env import apply_common_env

ensure_bench_root_on_path()
apply_common_env()
configure_django_for_tests()
