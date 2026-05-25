"""GitHub URL helpers for developer environment deduplication."""

from __future__ import annotations


def normalize_github_url(url: str) -> str:
    """Canonical form for comparing duplicate repo submissions."""
    u = url.strip().rstrip("/")
    if u.lower().endswith(".git"):
        u = u[:-4]
    if u.startswith("http://"):
        u = "https://" + u[7:]
    elif not u.startswith("https://") and not u.startswith("http://"):
        u = f"https://{u}"
    return u.lower()
