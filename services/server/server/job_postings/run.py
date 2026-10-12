import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Mapping, Optional, Tuple

import requests
from django.db import transaction
from django.db.models import Q
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
LEASE_TIMEOUT_SECONDS = 180  # 3 minutes - if a message is stuck in SENDING longer, re-queue it
MAX_MESSAGES_PER_RUN = 5  # Limit messages per run to stay under gunicorn timeout
RUN_DEADLINE_SECONDS = 20  # Stop claiming new messages after this many seconds


@dataclass
class RunResult:
    """Result of a run() call with counts for reporting and exit code determination."""

    enqueue_errors: List[Exception]
    sent: int
    deferred: int
    dead: int
    stale_recovered: int

    @property
    def failed(self) -> bool:
        """True if the run had any failures that should cause nonzero exit."""
        return len(self.enqueue_errors) > 0 or self.dead > 0


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


def enqueue_source(source: Source, webhooks: Mapping[str, str], now: int) -> Tuple[int, bool]:
    """
    Fetches new listings and enqueues Discord messages in the outbox.

    Returns (enqueued_count, is_seed). Raises RuntimeError if the webhook is not configured.
    The webhook is validated BEFORE modifying any state to fail fast.
    """
    webhook_url = webhooks.get(source.webhook)
    if not webhook_url:
        raise RuntimeError(f"{source.webhook} is not set")

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


def recover_stale_leases() -> int:
    """
    Re-queue messages stuck in SENDING past the lease timeout.

    Returns the count of recovered messages. These represent potential duplicates (the original
    send may have succeeded before the worker died), but at-least-once delivery is preferred
    over silent drops since Discord webhooks have no idempotency key.
    """
    cutoff = timezone.now() - timedelta(seconds=LEASE_TIMEOUT_SECONDS)
    stale = OutboxMessage.objects.filter(
        status=OutboxMessage.Status.SENDING,
        claimed_at__lt=cutoff,
    )
    count = stale.count()
    if count > 0:
        stale.update(
            status=OutboxMessage.Status.PENDING,
            claimed_at=None,
            last_error="Re-queued after stale lease (possible duplicate)",
        )
        for msg_id in stale.values_list("id", flat=True):
            logger.warning("Outbox %d re-queued after stale lease (at-least-once delivery)", msg_id)
    return count


def _claim_message_for_sending(webhooks: Mapping[str, str]) -> Optional[OutboxMessage]:
    """
    Claim one pending message by setting status=SENDING and claimed_at.

    Returns the claimed message (with webhook_url attached as an attribute for convenience),
    or None if no eligible messages exist. Messages with missing webhook config are skipped
    (not claimed, not counted toward attempts) - they stay pending until config is restored.
    """
    now = timezone.now()

    with transaction.atomic():
        msg = (
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                Q(next_attempt_at__lte=now) | Q(next_attempt_at__isnull=True),
                status=OutboxMessage.Status.PENDING,
            )
            .order_by("created_at")
            .first()
        )
        if msg is None:
            return None

        webhook_url = webhooks.get(msg.webhook_env_var)
        if not webhook_url:
            # Missing config: defer without counting as an attempt
            # Message stays pending until config is restored
            msg.next_attempt_at = now + timedelta(minutes=30)
            msg.last_error = f"{msg.webhook_env_var} is not set (config missing, not an attempt)"
            msg.save()
            logger.warning("Outbox %d skipped: %s not configured", msg.id, msg.webhook_env_var)
            return None

        # Claim the message
        msg.status = OutboxMessage.Status.SENDING
        msg.claimed_at = now
        msg.save()

    # Attach webhook_url for caller convenience (not persisted)
    msg._webhook_url = webhook_url
    return msg


def _complete_send(msg: OutboxMessage, result) -> Tuple[int, int, int]:
    """
    Update message status after send attempt. Returns (sent, deferred, dead) deltas.

    Called in a separate short transaction after the Discord call completes.
    """
    sent = deferred = dead = 0

    with transaction.atomic():
        # Re-fetch to ensure we have the latest state
        msg = OutboxMessage.objects.select_for_update().get(pk=msg.pk)

        if isinstance(result, SendSuccess):
            msg.status = OutboxMessage.Status.SENT
            msg.sent_at = timezone.now()
            msg.claimed_at = None
            msg.save()
            sent = 1
        elif isinstance(result, SendRateLimited):
            msg.status = OutboxMessage.Status.PENDING
            msg.attempt_count += 1
            msg.next_attempt_at = timezone.now() + timedelta(seconds=result.retry_after)
            msg.last_error = f"Rate limited, retry after {result.retry_after}s"
            msg.claimed_at = None
            msg.save()
            deferred = 1
            logger.info("Outbox %d rate-limited, deferred %.1fs", msg.id, result.retry_after)
        else:
            msg.attempt_count += 1
            msg.last_error = f"HTTP {result.status_code}: {result.message}"
            msg.claimed_at = None
            if msg.attempt_count >= MAX_DELIVERY_ATTEMPTS:
                msg.status = OutboxMessage.Status.DEAD
                dead = 1
                logger.warning("Outbox %d dead-lettered: %s", msg.id, msg.last_error)
            else:
                msg.status = OutboxMessage.Status.PENDING
                backoff = min(2 ** (msg.attempt_count - 1), 60)
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


def deliver_pending(webhooks: Mapping[str, str]) -> Tuple[int, int, int, int]:
    """
    Delivers pending outbox messages to Discord.

    Returns (sent, deferred, dead, stale_recovered). Enforces per-run limits:
    - MAX_MESSAGES_PER_RUN: stop after this many messages
    - RUN_DEADLINE_SECONDS: stop claiming new messages after this time

    Uses at-least-once delivery semantics:
    1. Claim: set status=SENDING with claimed_at timestamp (short transaction)
    2. Send: make Discord call OUTSIDE any transaction
    3. Complete: update status based on result (short transaction)

    If a worker dies between claim and complete, recover_stale_leases() will re-queue the
    message after LEASE_TIMEOUT_SECONDS, accepting a possible duplicate.
    """
    # First, recover any stale leases from previous crashed runs
    stale_recovered = recover_stale_leases()

    sent = 0
    deferred = 0
    dead = 0
    messages_processed = 0
    run_start = time.monotonic()

    while messages_processed < MAX_MESSAGES_PER_RUN:
        # Check deadline before claiming another message
        elapsed = time.monotonic() - run_start
        if elapsed >= RUN_DEADLINE_SECONDS:
            logger.info("Delivery deadline reached (%.1fs), stopping", elapsed)
            break

        # Claim a message (short transaction)
        msg = _claim_message_for_sending(webhooks)
        if msg is None:
            break

        # Send OUTSIDE transaction - this is the critical fix
        # If we crash here, the message stays in SENDING and will be recovered
        result = try_send_payload(msg._webhook_url, msg.payload)

        # Complete the send (short transaction)
        s, d, x = _complete_send(msg, result)
        sent += s
        deferred += d
        dead += x
        messages_processed += 1

    return sent, deferred, dead, stale_recovered


def run(webhooks: Mapping[str, str], now: Optional[int] = None) -> RunResult:
    """
    Enqueues new listings from each source and delivers pending outbox messages.

    Returns a RunResult with counts and error information. The caller should check
    result.failed to determine exit code.
    """
    now_ts = int(time.time()) if now is None else now
    errors: List[Exception] = []

    for source in SOURCES:
        try:
            enqueued, is_seed = enqueue_source(source, webhooks, now_ts)
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

    sent, deferred, dead, stale_recovered = deliver_pending(webhooks)
    if sent > 0 or deferred > 0 or dead > 0 or stale_recovered > 0:
        logger.info(
            "Delivery: %d sent, %d deferred, %d dead, %d stale recovered",
            sent,
            deferred,
            dead,
            stale_recovered,
        )

    return RunResult(
        enqueue_errors=errors,
        sent=sent,
        deferred=deferred,
        dead=dead,
        stale_recovered=stale_recovered,
    )
