import logging
import time
from typing import List, Mapping, Optional

import requests
from django.db import transaction

from .discord import REQUEST_TIMEOUT, build_payloads, post_payload
from .models import SourceState
from .selection import select_new
from .sources import SOURCES, Source, parse_listing

logger = logging.getLogger(__name__)


def fetch_listings(source: Source, etag: Optional[str]):
    headers = {"If-None-Match": etag} if etag else {}
    res = requests.get(source.url, headers=headers, timeout=REQUEST_TIMEOUT)
    if res.status_code == 304:
        return None
    if not res.ok:
        raise RuntimeError(f"Fetching {source.id} failed: {res.status_code}")
    raw = res.json()
    if not isinstance(raw, list):
        raise RuntimeError(f"Fetching {source.id} failed: body is not an array")
    listings = [listing for listing in map(parse_listing, raw) if listing is not None]
    return res.headers.get("etag", ""), listings


def run_source(source: Source, webhooks: Mapping[str, str], now: int) -> None:
    """
    Fetches new listings and posts them to Discord.

    The DB update happens before Discord posts to prevent duplicates: if Discord fails mid-batch,
    the listings are already marked as seen, so they won't be re-posted on the next run. The
    trade-off is that a Discord failure may cause some listings to never be posted, but this is
    preferable to spamming the channel with duplicates.
    """
    webhook_url = webhooks.get(source.webhook)
    if not webhook_url:
        raise RuntimeError(f"{source.webhook} is not set")

    # Phase 1: Inside a transaction, determine what to post and update the DB.
    # Holding the row lock makes an overlapping run wait here instead of racing.
    with transaction.atomic():
        before = SourceState.objects.select_for_update().filter(pk=source.id).first()
        result = fetch_listings(source, before.etag if before else None)
        if result is None:
            return
        etag, listings = result
        fresh, seen, deferred = select_new(listings, source, before.seen if before else None, now)
        is_seed = before is None
        # Keeping the old etag forces a refetch next run, so listings held back by the cap are not
        # stuck behind a 304.
        kept_etag = (before.etag if before else "") if deferred else etag
        SourceState.objects.update_or_create(
            source_id=source.id, defaults={"etag": kept_etag, "seen": seen}
        )

    # Phase 2: Post to Discord outside the transaction. If this fails, the listings are already
    # marked as seen, preventing duplicates on retry.
    payloads = build_payloads(fresh, source)
    for payload in payloads:
        post_payload(webhook_url, payload)
    logger.info("%s: posted %d%s", source.id, len(fresh), " (seed run)" if is_seed else "")


def run(webhooks: Mapping[str, str], now: Optional[int] = None) -> List[Exception]:
    """Posts each source's new listings and returns the errors of the sources that failed."""
    now = int(time.time()) if now is None else now
    errors: List[Exception] = []
    for source in SOURCES:
        try:
            run_source(source, webhooks, now)
        except Exception as err:
            logger.exception("%s failed", source.id)
            errors.append(err)
    return errors
