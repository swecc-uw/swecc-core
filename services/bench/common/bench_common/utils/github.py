"""GitHub URL helpers for developer environment deduplication."""

from __future__ import annotations

import re

# Only canonical GitHub HTTPS URLs are accepted for cloning. This is a
# trust boundary: arbitrary URLs (file://, git://, ssh://, attacker.com)
# could deliver malicious requirements.txt / setup.py that runs as root
# inside the sandbox container during pip install.
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
)


class InvalidGithubUrl(ValueError):
    """Raised when a submitted repo URL is not a valid github.com HTTPS URL."""


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


def validate_github_url(url: str) -> str:
    """Return canonical URL if it points at github.com, else raise.

    Rejects non-github hosts, ssh/file/git schemes, repo names with shell
    metacharacters, and anything that doesn't look like ``owner/repo``.
    Call this *before* handing the URL to ``git clone`` in the sandbox.
    """
    canonical = normalize_github_url(url)
    if not _GITHUB_URL_RE.match(canonical):
        raise InvalidGithubUrl(
            f"Only https://github.com/<owner>/<repo> URLs are accepted; got {url!r}"
        )
    return canonical
