"""
Storage backend dispatcher.

Reads ORCH_DB_BACKEND (default: "django") at first attribute access and routes
all calls to the matching module:

  "django"  →  bench_common.storage.django_store  (Django ORM + Postgres)
  "sqlite"  →  bench_common.storage.sqlite_store  (aiosqlite, zero-dep local dev)

Callers are unchanged:

    from bench_common.storage import database as db
    await db.get_domain(domain_id)          # works with either backend

To switch backends without Docker, set the environment variable before starting:

    ORCH_DB_BACKEND=sqlite python -m bench_common.inference.bench ...

Future backends (e.g. Supabase REST) can be added here without touching callers.
"""

from __future__ import annotations

import importlib


def __getattr__(name: str):
    from bench_common.config import settings

    if settings.db_backend == "sqlite":
        mod = importlib.import_module("bench_common.storage.sqlite_store")
    else:
        mod = importlib.import_module("bench_common.storage.django_store")

    attr = getattr(mod, name)
    # Cache resolved attribute so subsequent accesses skip __getattr__.
    globals()[name] = attr
    return attr
