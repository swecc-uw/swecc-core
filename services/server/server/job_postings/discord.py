import re
from dataclasses import dataclass
from typing import List, Optional, Union

import requests

from .sources import Listing, Source

MAX_ENTRIES = 10
MAX_DESCRIPTION = 4096
MAX_LINK_TEXT = 200
SHOWN_LOCATIONS = 3
ENTRY_SEPARATOR = "\n\n"
REQUEST_TIMEOUT = 10


@dataclass
class SendSuccess:
    """Discord accepted the message."""

    pass


@dataclass
class SendRateLimited:
    """Discord returned 429. retry_after is in seconds."""

    retry_after: float


@dataclass
class SendError:
    """Discord rejected the message with a non-retryable error."""

    status_code: int
    message: str


SendResult = Union[SendSuccess, SendRateLimited, SendError]


def _truncate(s: str, max_length: int) -> str:
    return f"{s[: max_length - 1]}…" if len(s) > max_length else s


def _escape_markdown(s: str) -> str:
    return re.sub(r"[\\\[\]*_`~|]", r"\\\g<0>", s)


def _format_locations(locations: List[str]) -> str:
    shown = " · ".join(locations[:SHOWN_LOCATIONS])
    extra = len(locations) - SHOWN_LOCATIONS
    return f"{shown} · +{extra} more" if extra > 0 else shown


def build_entry(listing: Listing) -> str:
    details = [
        _format_locations(listing.locations),
        ", ".join(listing.terms),
        ", ".join(listing.degrees),
        # Upstream marks unknown sponsorship as "Other", which carries no information.
        "" if listing.sponsorship == "Other" else listing.sponsorship,
        f"<t:{listing.date_posted}:R>",
    ]
    text = _escape_markdown(_truncate(f"{listing.company} · {listing.title}", MAX_LINK_TEXT))
    return f"**[{text}]({listing.url})**\n{' · '.join(d for d in details if d)}"


# One embed holds the whole batch: Discord sizes each embed to its own content, so a stack of
# per-listing embeds renders at ragged widths.
def build_payloads(listings: List[Listing], source: Source) -> List[dict]:
    batches: List[List[str]] = []
    size = 0
    for entry in map(build_entry, listings):
        added = len(ENTRY_SEPARATOR) + len(entry)
        if not batches or len(batches[-1]) == MAX_ENTRIES or size + added > MAX_DESCRIPTION:
            batches.append([entry])
            size = len(entry)
        else:
            batches[-1].append(entry)
            size += added
    return [
        {
            "embeds": [{"color": source.color, "description": ENTRY_SEPARATOR.join(batch)}],
            "allowed_mentions": {"parse": []},
        }
        for batch in batches
    ]


def try_send_payload(webhook_url: str, payload: dict) -> SendResult:
    """
    Attempt to send a payload to Discord once, returning the result.

    Returns SendSuccess if Discord accepted it, SendRateLimited if we hit a 429 (with retry_after),
    or SendError for other failures. Does not retry or sleep.
    """
    url = f"{webhook_url}{'&' if '?' in webhook_url else '?'}wait=true"
    try:
        res = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        return SendError(status_code=0, message=str(e))

    if res.ok:
        return SendSuccess()

    if res.status_code == 429:
        try:
            retry_after = res.json().get("retry_after", 60)
        except ValueError:
            retry_after = 60
        return SendRateLimited(retry_after=float(retry_after))

    return SendError(status_code=res.status_code, message=res.text[:500])
