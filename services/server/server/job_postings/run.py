import logging
import time
from datetime import timedelta
from typing import List, Mapping, Optional, Tuple

import requests
from django.db import transaction
from django.utils import timezone

from .discord import (
    REQUEST_TIMEOUT,
    SendError,
    SendRateLimited,
    SendSuccess,
    build_payloads,
    try_send_payload,
)
from .models import OutboxMessage, SourceState
from .selection import select_new
from .sources import SOURCES, Source, parse_listing

logger = logging.getLogger(__name__)

MAX_DELIVERY_ATTEMPTS = 10


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


def enqueue_source(source: Source, now: int) -> Tuple[int, bool]:
    """
    Fetches new listings and enqueues Discord messages in the outbox.

    Returns (enqueued_count, is_seed). The outbox messages and the SourceState update are in the
    same transaction, ensuring atomicity: if the transaction fails, neither the messages nor the
    seen-IDs update are persisted.
    """
    with transaction.atomic():
        before = SourceState.objects.select_for_update().filter(pk=source.id).first()
        result = fetch_listings(source, before.etag if before else None)
        if result is None:
            return 0, False
        etag, listings = result
        fresh, seen, deferred = select_new(listings, source, before.seen if before else None, now)
        is_seed = before is None

        payloads = build_payloads(fresh, source)
        enqueue_time = timezone.now()
        for payload in payloads:
            OutboxMessage.objects.create(
                source_id=source.id,
                webhook_env_var=source.webhook,
                payload=payload,
                next_attempt_at=enqueue_time,
            )

        kept_etag = (before.etag if before else "") if deferred else etag
        SourceState.objects.update_or_create(
            source_id=source.id, defaults={"etag": kept_etag, "seen": seen}
        )

    return len(payloads), is_seed


def _claim_pending_message() -> Optional[OutboxMessage]:
    """
    Atomically claim one pending message for delivery.

    Uses select_for_update(skip_locked=True) so concurrent workers skip messages that are
    already being processed by another worker. Returns None if no claimable messages exist.
    """
    from django.db.models import Q

    now = timezone.now()
    return (
        OutboxMessage.objects.select_for_update(skip_locked=True)
        .filter(
            Q(next_attempt_at__lte=now) | Q(next_attempt_at__isnull=True),
            status=OutboxMessage.Status.PENDING,
        )
        .order_by("created_at")
        .first()
    )


def deliver_pending(webhooks: Mapping[str, str]) -> Tuple[int, int, int]:
    """
    Delivers pending outbox messages to Discord.

    Returns (sent_count, deferred_count, dead_count). Each message is processed independently:
    - Success: marked as sent
    - Rate limited (429): deferred with next_attempt_at set to now + retry_after
    - Error: attempt_count incremented; dead-lettered after MAX_DELIVERY_ATTEMPTS

    Concurrency-safe: uses select_for_update(skip_locked=True) to claim one message at a time.
    Concurrent workers will skip messages that are already being processed, preventing duplicate
    sends. Does not sleep or retry in-process, staying within the gunicorn timeout.
    """
    sent = 0
    deferred = 0
    dead = 0

    while True:
        with transaction.atomic():
            msg = _claim_pending_message()
            if msg is None:
                break

            webhook_url = webhooks.get(msg.webhook_env_var)
            if not webhook_url:
                msg.attempt_count += 1
                msg.last_error = f"{msg.webhook_env_var} is not set"
                if msg.attempt_count >= MAX_DELIVERY_ATTEMPTS:
                    msg.status = OutboxMessage.Status.DEAD
                    dead += 1
                    logger.warning("Outbox %d dead-lettered: %s", msg.id, msg.last_error)
                else:
                    # Defer retry - config issue unlikely to resolve within same run
                    msg.next_attempt_at = timezone.now() + timedelta(minutes=30)
                msg.save()
                continue

            result = try_send_payload(webhook_url, msg.payload)

            if isinstance(result, SendSuccess):
                msg.status = OutboxMessage.Status.SENT
                msg.sent_at = timezone.now()
                msg.save()
                sent += 1
            elif isinstance(result, SendRateLimited):
                msg.attempt_count += 1
                msg.next_attempt_at = timezone.now() + timedelta(seconds=result.retry_after)
                msg.last_error = f"Rate limited, retry after {result.retry_after}s"
                msg.save()
                deferred += 1
                logger.info("Outbox %d rate-limited, deferred %.1fs", msg.id, result.retry_after)
            else:
                msg.attempt_count += 1
                msg.last_error = f"HTTP {result.status_code}: {result.message}"
                if msg.attempt_count >= MAX_DELIVERY_ATTEMPTS:
                    msg.status = OutboxMessage.Status.DEAD
                    dead += 1
                    logger.warning("Outbox %d dead-lettered: %s", msg.id, msg.last_error)
                else:
                    # Defer retry with exponential backoff (1min, 2min, 4min, ...)
                    backoff = min(2 ** (msg.attempt_count - 1), 60)  # Cap at 60 minutes
                    msg.next_attempt_at = timezone.now() + timedelta(minutes=backoff)
                    logger.warning(
                        "Outbox %d failed (attempt %d), retry in %dm: %s",
                        msg.id,
                        msg.attempt_count,
                        backoff,
                        msg.last_error,
                    )
                msg.save()

    return sent, deferred, dead


def run(webhooks: Mapping[str, str], now: Optional[int] = None) -> List[Exception]:
    """
    Enqueues new listings from each source and delivers pending outbox messages.

    Returns the errors from sources that failed to enqueue. Delivery errors are logged but not
    returned (they leave messages pending for the next run).
    """
    now_ts = int(time.time()) if now is None else now
    errors: List[Exception] = []
    total_enqueued = 0

    for source in SOURCES:
        try:
            enqueued, is_seed = enqueue_source(source, now_ts)
            total_enqueued += enqueued
            if enqueued > 0 or is_seed:
                logger.info(
                    "%s: enqueued %d%s",
                    source.id,
                    enqueued,
                    " (seed run)" if is_seed else "",
                )
        except Exception as err:
            logger.exception("%s failed to enqueue", source.id)
            errors.append(err)

    sent, deferred, dead = deliver_pending(webhooks)
    if sent > 0 or deferred > 0 or dead > 0:
        logger.info("Delivery: %d sent, %d deferred, %d dead", sent, deferred, dead)

    return errors
