from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .discord import (
    SendError,
    SendRateLimited,
    SendSuccess,
    build_entry,
    build_payloads,
    try_send_payload,
)
from .models import OutboxMessage, SourceState
from .run import (
    LEASE_TIMEOUT_SECONDS,
    MAX_DELIVERY_ATTEMPTS,
    MAX_MESSAGES_PER_RUN,
    RunResult,
    _claim_message_for_sending,
    deliver_pending,
    enqueue_source,
    recover_stale_leases,
    run,
)
from .selection import MAX_POSTS_PER_SOURCE, WINDOW_SECONDS, select_new
from .sources import SOURCES, Listing, parse_listing

NOW = 10_000_000
INTERNSHIPS, NEW_GRAD = SOURCES
INTERN_HOOK = "https://discord.test/api/webhooks/1/intern"
GRAD_HOOK = "https://discord.test/api/webhooks/2/grad"
WEBHOOKS = {"DISCORD_WEBHOOK_INTERNSHIPS": INTERN_HOOK, "DISCORD_WEBHOOK_NEW_GRAD": GRAD_HOOK}

LISTING = Listing(
    id="a",
    company="Acme",
    title="Software Engineer Intern",
    url="https://example.com/a",
    locations=["Austin, TX"],
    terms=["Summer 2027"],
    degrees=["Bachelor's"],
    category="Software",
    sponsorship="Other",
    date_posted=1_000_000,
    active=True,
    visible=True,
)


def listing(**over):
    return replace(LISTING, **over)


def raw_entry(listing_id, **over):
    return {
        "source": "Simplify",
        "category": "Software",
        "company_name": "Acme",
        "id": listing_id,
        "title": "Engineer",
        "active": True,
        "terms": ["Summer 2027"],
        "date_updated": 1,
        "date_posted": 1_000_000,
        "url": f"https://example.com/{listing_id}",
        "locations": ["Austin, TX"],
        "company_url": "https://simplify.jobs/c/Acme",
        "is_visible": True,
        "sponsorship": "Other",
        "degrees": ["Bachelor's"],
        **over,
    }


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.text = "" if body is None else str(body)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self.body is None:
            raise ValueError("no body")
        return self.body


def listings_file(*ids):
    return FakeResponse(
        body=[raw_entry(i, date_posted=NOW - 60) for i in ids], headers={"etag": '"v2"'}
    )


UNCHANGED = FakeResponse(status_code=304)
ACCEPTED = FakeResponse(body={})


class FakeHttp:
    """Stands in for `requests`, answering each URL from `responses` and recording the calls."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def _respond(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        key = url.split("?")[0]
        if key not in self.responses:
            raise AssertionError(f"unexpected request {url}")
        return self.responses[key]

    def get(self, url, **kwargs):
        return self._respond(url, **kwargs)

    def post(self, url, **kwargs):
        return self._respond(url, **kwargs)

    def descriptions(self, hook):
        return [
            call["json"]["embeds"][0]["description"]
            for call in self.calls
            if call["url"].startswith(hook)
        ]


def entry_counts(payloads):
    return [len(p["embeds"][0]["description"].split("\n\n")) for p in payloads]


class ParseListingTests(SimpleTestCase):
    def test_maps_a_real_entry(self):
        self.assertEqual(
            parse_listing(raw_entry("x1", sponsorship="Offers Sponsorship")),
            Listing(
                id="x1",
                company="Acme",
                title="Engineer",
                url="https://example.com/x1",
                locations=["Austin, TX"],
                terms=["Summer 2027"],
                degrees=["Bachelor's"],
                category="Software",
                sponsorship="Offers Sponsorship",
                date_posted=1_000_000,
                active=True,
                visible=True,
            ),
        )

    def test_drops_malformed_entries(self):
        self.assertIsNone(parse_listing(None))
        self.assertIsNone(parse_listing("nope"))
        self.assertIsNone(parse_listing({"id": "x", "url": "u"}))
        self.assertIsNone(parse_listing(raw_entry("x", date_posted="yesterday")))
        self.assertIsNone(parse_listing(raw_entry("x", date_posted=True)))
        self.assertIsNone(parse_listing(raw_entry("x", date_posted=float("nan"))))

    def test_tolerates_missing_optional_fields(self):
        parsed = parse_listing({"id": "x", "url": "u", "date_posted": 5})
        self.assertEqual(parsed.locations, [])
        self.assertEqual(parsed.terms, [])
        self.assertEqual(parsed.company, "")
        self.assertFalse(parsed.active)
        self.assertFalse(parsed.visible)


class SourceFilterTests(SimpleTestCase):
    def test_matches_a_software_summer_2027_internship(self):
        self.assertTrue(INTERNSHIPS.matches(listing()))

    def test_rejects_hardware(self):
        self.assertFalse(INTERNSHIPS.matches(listing(category="Hardware")))

    def test_rejects_summer_2026_only_terms(self):
        self.assertFalse(INTERNSHIPS.matches(listing(terms=["Summer 2026"])))

    def test_rejects_inactive_and_hidden_listings(self):
        self.assertFalse(INTERNSHIPS.matches(listing(active=False)))
        self.assertFalse(INTERNSHIPS.matches(listing(visible=False)))

    def test_matches_new_grad_software_without_terms(self):
        self.assertTrue(NEW_GRAD.matches(listing(terms=[])))
        self.assertFalse(NEW_GRAD.matches(listing(terms=[], category="Quant")))


class SelectNewTests(SimpleTestCase):
    def recent(self, listing_id, ago):
        return listing(id=listing_id, date_posted=NOW - ago)

    def test_seeds_on_first_run_posts_nothing_and_records_candidates(self):
        old = listing(id="old", date_posted=NOW - WINDOW_SECONDS - 1)
        fresh, seen, _ = select_new(
            [self.recent("a", 100), self.recent("b", 50), old], INTERNSHIPS, None, NOW
        )
        self.assertEqual(fresh, [])
        self.assertEqual(seen, {"a": NOW - 100, "b": NOW - 50})

    def test_second_run_posts_only_the_new_ids_oldest_first(self):
        listings = [self.recent("a", 100), self.recent("c", 10), self.recent("b", 50)]
        fresh, seen, deferred = select_new(listings, INTERNSHIPS, {"a": NOW - 100}, NOW)
        self.assertEqual([item.id for item in fresh], ["b", "c"])
        self.assertFalse(deferred)
        self.assertEqual(seen, {"a": NOW - 100, "b": NOW - 50, "c": NOW - 10})

    def test_prunes_seen_entries_older_than_the_window(self):
        prev = {"stale": NOW - WINDOW_SECONDS - 5, "a": NOW - 100}
        _, seen, _ = select_new([self.recent("a", 100)], INTERNSHIPS, prev, NOW)
        self.assertEqual(seen, {"a": NOW - 100})

    def test_ignores_non_matching_listings(self):
        hardware = listing(id="hw", category="Hardware", date_posted=NOW - 5)
        fresh, seen, _ = select_new([hardware], INTERNSHIPS, {}, NOW)
        self.assertEqual(fresh, [])
        self.assertEqual(seen, {})

    def test_leaves_overflow_beyond_the_cap_unseen(self):
        listings = [self.recent(f"id{i}", 1000 - i) for i in range(MAX_POSTS_PER_SOURCE + 2)]
        fresh, seen, deferred = select_new(listings, INTERNSHIPS, {}, NOW)
        self.assertEqual(len(fresh), MAX_POSTS_PER_SOURCE)
        self.assertEqual(len(seen), MAX_POSTS_PER_SOURCE)
        self.assertNotIn(f"id{MAX_POSTS_PER_SOURCE + 1}", seen)
        self.assertTrue(deferred)


class BuildEntryTests(SimpleTestCase):
    def test_links_the_company_and_role_then_lists_every_known_detail(self):
        entry = build_entry(
            listing(
                company="Johnson Controls",
                title="Software Engineer Co-op",
                url="https://example.com/j",
                locations=["Burlington, MA"],
                terms=["Winter 2027"],
                sponsorship="Offers Sponsorship",
                date_posted=1791504000,
            )
        )
        self.assertEqual(
            entry,
            "**[Johnson Controls · Software Engineer Co-op](https://example.com/j)**\n"
            "Burlington, MA · Winter 2027 · Bachelor's · Offers Sponsorship · <t:1791504000:R>",
        )

    def test_omits_empty_details_and_unknown_sponsorship_and_summarizes_many_locations(self):
        entry = build_entry(
            listing(terms=[], degrees=[], locations=["A", "B", "C", "D", "E"], date_posted=5)
        )
        self.assertEqual(entry.split("\n")[1], "A · B · C · +2 more · <t:5:R>")

    def test_escapes_markdown_in_the_link_text(self):
        entry = build_entry(listing(company="A*B", title="Intern [Remote]", url="https://e.com/x"))
        self.assertEqual(entry.split("\n")[0], "**[A\\*B · Intern \\[Remote\\]](https://e.com/x)**")


class BuildPayloadsTests(SimpleTestCase):
    def test_puts_a_batch_in_one_embed_coloured_by_source(self):
        listings = [
            listing(id="1", company="Acme", date_posted=1),
            listing(id="2", company="Globex", date_posted=2),
        ]
        self.assertEqual(
            build_payloads(listings, NEW_GRAD),
            [
                {
                    "embeds": [
                        {
                            "color": 0x57F287,
                            "description": "**[Acme · Software Engineer Intern](https://example.com/a)**\n"
                            "Austin, TX · Summer 2027 · Bachelor's · <t:1:R>\n\n"
                            "**[Globex · Software Engineer Intern](https://example.com/a)**\n"
                            "Austin, TX · Summer 2027 · Bachelor's · <t:2:R>",
                        }
                    ],
                    "allowed_mentions": {"parse": []},
                }
            ],
        )

    def test_splits_23_listings_into_messages_of_10_10_and_3(self):
        listings = [listing(id=f"id{i}") for i in range(23)]
        self.assertEqual(entry_counts(build_payloads(listings, INTERNSHIPS)), [10, 10, 3])

    def test_starts_a_new_message_before_the_description_passes_4096_characters(self):
        url = f"https://example.com/{'x' * 900}"
        payloads = build_payloads([listing(id=f"id{i}", url=url) for i in range(6)], INTERNSHIPS)
        self.assertEqual(entry_counts(payloads), [4, 2])
        self.assertTrue(all(len(p["embeds"][0]["description"]) <= 4096 for p in payloads))

    def test_returns_nothing_for_no_listings(self):
        self.assertEqual(build_payloads([], INTERNSHIPS), [])


class TrySendPayloadTests(SimpleTestCase):
    def test_returns_success_when_discord_accepts(self):
        with patch("job_postings.discord.requests.post", return_value=ACCEPTED):
            result = try_send_payload(INTERN_HOOK, {"embeds": []})
        self.assertIsInstance(result, SendSuccess)

    def test_returns_rate_limited_with_retry_after(self):
        limited = FakeResponse(status_code=429, body={"retry_after": 42.5})
        with patch("job_postings.discord.requests.post", return_value=limited):
            result = try_send_payload(INTERN_HOOK, {"embeds": []})
        self.assertIsInstance(result, SendRateLimited)
        self.assertEqual(result.retry_after, 42.5)

    def test_returns_error_when_discord_rejects(self):
        rejected = FakeResponse(status_code=400, body="bad embed")
        with patch("job_postings.discord.requests.post", return_value=rejected):
            result = try_send_payload(INTERN_HOOK, {"embeds": []})
        self.assertIsInstance(result, SendError)
        self.assertEqual(result.status_code, 400)
        self.assertIn("bad embed", result.message)

    def test_returns_error_on_network_exception(self):
        import requests

        with patch("job_postings.discord.requests.post", side_effect=requests.Timeout("timed out")):
            result = try_send_payload(INTERN_HOOK, {"embeds": []})
        self.assertIsInstance(result, SendError)
        self.assertEqual(result.status_code, 0)
        self.assertIn("timed out", result.message)


class EnqueueSourceTests(TestCase):
    def setUp(self):
        logging_patcher = patch("job_postings.run.logger")
        logging_patcher.start()
        self.addCleanup(logging_patcher.stop)

    def test_validates_webhook_before_modifying_state(self):
        # Missing webhook should fail fast without seeding or enqueueing
        http = FakeHttp({INTERNSHIPS.url: listings_file("a", "b")})
        with patch("job_postings.run.requests", http):
            with self.assertRaisesMessage(RuntimeError, "DISCORD_WEBHOOK_INTERNSHIPS is not set"):
                enqueue_source(INTERNSHIPS, {}, NOW)
        # No state should have been created
        self.assertFalse(SourceState.objects.filter(pk=INTERNSHIPS.id).exists())
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_enqueues_messages_atomically_with_state_update(self):
        http = FakeHttp({INTERNSHIPS.url: listings_file("a", "b")})
        with patch("job_postings.run.requests", http):
            enqueued, is_seed = enqueue_source(INTERNSHIPS, WEBHOOKS, NOW)

        self.assertEqual(enqueued, 0)  # Seed run enqueues nothing
        self.assertTrue(is_seed)
        self.assertEqual(OutboxMessage.objects.count(), 0)
        state = SourceState.objects.get(pk=INTERNSHIPS.id)
        self.assertEqual(state.seen, {"a": NOW - 60, "b": NOW - 60})

    def test_second_run_enqueues_new_listings(self):
        SourceState.objects.create(source_id=INTERNSHIPS.id, etag='"v1"', seen={"a": NOW - 60})
        http = FakeHttp({INTERNSHIPS.url: listings_file("a", "b", "c")})
        with patch("job_postings.run.requests", http):
            enqueued, is_seed = enqueue_source(INTERNSHIPS, WEBHOOKS, NOW)

        self.assertEqual(enqueued, 1)  # One message with 2 listings
        self.assertFalse(is_seed)
        msg = OutboxMessage.objects.get()
        self.assertEqual(msg.source_id, INTERNSHIPS.id)
        self.assertEqual(msg.status, OutboxMessage.Status.PENDING)
        self.assertIn("example.com/b", msg.payload["embeds"][0]["description"])
        self.assertIn("example.com/c", msg.payload["embeds"][0]["description"])


class StaleLeaseRecoveryTests(TestCase):
    def setUp(self):
        logging_patcher = patch("job_postings.run.logger")
        logging_patcher.start()
        self.addCleanup(logging_patcher.stop)

    def test_recovers_stale_sending_messages(self):
        # Message stuck in SENDING past the lease timeout
        stale_time = timezone.now() - timedelta(seconds=LEASE_TIMEOUT_SECONDS + 60)
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            status=OutboxMessage.Status.SENDING,
            claimed_at=stale_time,
        )
        recovered = recover_stale_leases()
        self.assertEqual(recovered, 1)
        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.PENDING)
        self.assertIsNone(msg.claimed_at)
        self.assertIn("stale lease", msg.last_error)

    def test_does_not_recover_fresh_sending_messages(self):
        # Message in SENDING but not past the lease timeout
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            status=OutboxMessage.Status.SENDING,
            claimed_at=timezone.now() - timedelta(seconds=30),  # Only 30s old
        )
        recovered = recover_stale_leases()
        self.assertEqual(recovered, 0)
        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.SENDING)

    def test_stale_recovery_included_in_delivery_stats(self):
        stale_time = timezone.now() - timedelta(seconds=LEASE_TIMEOUT_SECONDS + 60)
        OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            status=OutboxMessage.Status.SENDING,
            claimed_at=stale_time,
        )
        sent, deferred, dead, stale_recovered = deliver_pending(WEBHOOKS)
        self.assertEqual(stale_recovered, 1)


class DeliverPendingTests(TestCase):
    def setUp(self):
        logging_patcher = patch("job_postings.run.logger")
        logging_patcher.start()
        self.addCleanup(logging_patcher.stop)

    def test_delivers_pending_messages_and_marks_sent(self):
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": [{"description": "test"}]},
        )
        with patch("job_postings.run.try_send_payload", return_value=SendSuccess()):
            sent, deferred, dead, _ = deliver_pending(WEBHOOKS)

        self.assertEqual((sent, deferred, dead), (1, 0, 0))
        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.SENT)
        self.assertIsNotNone(msg.sent_at)
        self.assertIsNone(msg.claimed_at)  # Lease cleared after completion

    def test_claim_sets_sending_status_with_claimed_at(self):
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
        )
        before = timezone.now()
        claimed = _claim_message_for_sending(WEBHOOKS)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, msg.pk)

        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.SENDING)
        self.assertGreaterEqual(msg.claimed_at, before)

    def test_defers_rate_limited_messages_with_retry_after(self):
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
        )
        before = timezone.now()
        with patch(
            "job_postings.run.try_send_payload", return_value=SendRateLimited(retry_after=120)
        ):
            sent, deferred, dead, _ = deliver_pending(WEBHOOKS)

        self.assertEqual((sent, deferred, dead), (0, 1, 0))
        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.PENDING)
        self.assertEqual(msg.attempt_count, 1)
        self.assertGreaterEqual(msg.next_attempt_at, before + timedelta(seconds=119))

    def test_does_not_pick_up_deferred_messages_until_next_attempt_at(self):
        OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            next_attempt_at=timezone.now() + timedelta(hours=1),
        )
        with patch("job_postings.run.try_send_payload") as mock_send:
            deliver_pending(WEBHOOKS)
        mock_send.assert_not_called()

    def test_partial_failure_leaves_failed_messages_pending_with_backoff(self):
        msg1 = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": [{"description": "msg1"}]},
            next_attempt_at=timezone.now(),
        )
        msg2 = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": [{"description": "msg2"}]},
            next_attempt_at=timezone.now(),
        )

        def side_effect(url, payload):
            if "msg1" in payload["embeds"][0]["description"]:
                return SendSuccess()
            return SendError(status_code=500, message="boom")

        before = timezone.now()
        with patch("job_postings.run.try_send_payload", side_effect=side_effect):
            sent, deferred, dead, _ = deliver_pending(WEBHOOKS)

        self.assertEqual((sent, deferred, dead), (1, 0, 0))
        msg1.refresh_from_db()
        msg2.refresh_from_db()
        self.assertEqual(msg1.status, OutboxMessage.Status.SENT)
        self.assertEqual(msg2.status, OutboxMessage.Status.PENDING)
        self.assertEqual(msg2.attempt_count, 1)
        self.assertGreaterEqual(msg2.next_attempt_at, before + timedelta(seconds=55))

    def test_dead_letters_after_max_attempts(self):
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            attempt_count=MAX_DELIVERY_ATTEMPTS - 1,
        )
        with patch(
            "job_postings.run.try_send_payload",
            return_value=SendError(status_code=500, message="persistent failure"),
        ):
            sent, deferred, dead, _ = deliver_pending(WEBHOOKS)

        self.assertEqual((sent, deferred, dead), (0, 0, 1))
        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.DEAD)
        self.assertIn("persistent failure", msg.last_error)

    def test_no_duplicate_sends_on_rerun(self):
        OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            status=OutboxMessage.Status.SENT,
            sent_at=timezone.now(),
        )
        with patch("job_postings.run.try_send_payload") as mock_send:
            sent, deferred, dead, _ = deliver_pending(WEBHOOKS)
        mock_send.assert_not_called()
        self.assertEqual((sent, deferred, dead), (0, 0, 0))

    def test_missing_webhook_does_not_count_toward_attempts(self):
        # Missing webhook should defer without incrementing attempt_count
        msg = OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="MISSING_WEBHOOK",
            payload={"embeds": []},
            attempt_count=0,
        )
        with patch("job_postings.run.try_send_payload") as mock_send:
            sent, deferred, dead, _ = deliver_pending(WEBHOOKS)

        mock_send.assert_not_called()  # Should skip, not call Discord
        msg.refresh_from_db()
        self.assertEqual(msg.status, OutboxMessage.Status.PENDING)
        self.assertEqual(msg.attempt_count, 0)  # NOT incremented
        self.assertIn("not set", msg.last_error)
        self.assertIn("not an attempt", msg.last_error)
        # Should be deferred, not dead-lettered
        self.assertIsNotNone(msg.next_attempt_at)

    def test_max_messages_per_run_limit(self):
        # Create more messages than the per-run limit
        for i in range(MAX_MESSAGES_PER_RUN + 3):
            OutboxMessage.objects.create(
                source_id=INTERNSHIPS.id,
                webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
                payload={"embeds": [{"description": f"msg{i}"}]},
            )
        with patch("job_postings.run.try_send_payload", return_value=SendSuccess()):
            sent, _, _, _ = deliver_pending(WEBHOOKS)

        # Should stop at MAX_MESSAGES_PER_RUN
        self.assertEqual(sent, MAX_MESSAGES_PER_RUN)
        # Remaining messages still pending
        pending = OutboxMessage.objects.filter(status=OutboxMessage.Status.PENDING).count()
        self.assertEqual(pending, 3)


class RunResultTests(SimpleTestCase):
    def test_failed_when_enqueue_errors(self):
        result = RunResult(
            enqueue_errors=[RuntimeError("test")],
            sent=5,
            deferred=0,
            dead=0,
            stale_recovered=0,
        )
        self.assertTrue(result.failed)

    def test_failed_when_dead_lettered(self):
        result = RunResult(
            enqueue_errors=[],
            sent=5,
            deferred=0,
            dead=1,
            stale_recovered=0,
        )
        self.assertTrue(result.failed)

    def test_not_failed_when_all_success(self):
        result = RunResult(
            enqueue_errors=[],
            sent=5,
            deferred=2,
            dead=0,
            stale_recovered=1,
        )
        self.assertFalse(result.failed)


class RunTests(TestCase):
    def setUp(self):
        logging_patcher = patch("job_postings.run.logger")
        logging_patcher.start()
        self.addCleanup(logging_patcher.stop)

    def run_with(self, responses, webhooks=WEBHOOKS):
        http = FakeHttp(responses)
        with patch("job_postings.run.requests", http), patch("job_postings.discord.requests", http):
            result = run(webhooks, NOW)
        return http, result

    def seed(self, **seen_by_source):
        for source in SOURCES:
            SourceState.objects.create(
                source_id=source.id, etag='"v1"', seen=seen_by_source.get(source.id, {})
            )

    def state(self):
        return {s.source_id: {"etag": s.etag, "seen": s.seen} for s in SourceState.objects.all()}

    def test_seeds_on_first_run_without_posting(self):
        http, result = self.run_with(
            {INTERNSHIPS.url: listings_file("a"), NEW_GRAD.url: listings_file("b")}
        )
        self.assertEqual([call["url"] for call in http.calls], [INTERNSHIPS.url, NEW_GRAD.url])
        self.assertFalse(result.failed)
        self.assertEqual(
            self.state(),
            {
                "simplify-internships": {"etag": '"v2"', "seen": {"a": NOW - 60}},
                "simplify-new-grad": {"etag": '"v2"', "seen": {"b": NOW - 60}},
            },
        )

    def test_posts_each_sources_new_listings_to_its_own_webhook(self):
        self.seed(**{"simplify-internships": {"a": NOW - 60}})
        http, result = self.run_with(
            {
                INTERNSHIPS.url: listings_file("a", "i"),
                NEW_GRAD.url: listings_file("g"),
                INTERN_HOOK: ACCEPTED,
                GRAD_HOOK: ACCEPTED,
            }
        )
        self.assertFalse(result.failed)
        self.assertEqual(result.sent, 2)
        self.assertEqual(len(http.descriptions(INTERN_HOOK)), 1)
        self.assertIn("https://example.com/i)", http.descriptions(INTERN_HOOK)[0])

    def test_missing_webhook_fails_source_without_modifying_state(self):
        # No state exists yet
        http, result = self.run_with(
            {
                INTERNSHIPS.url: listings_file("a"),
                NEW_GRAD.url: listings_file("b"),  # Provide valid response for NEW_GRAD too
            },
            webhooks={"DISCORD_WEBHOOK_NEW_GRAD": GRAD_HOOK},  # Missing INTERNSHIPS webhook
        )
        self.assertTrue(result.failed)
        self.assertEqual(len(result.enqueue_errors), 1)
        self.assertIn("DISCORD_WEBHOOK_INTERNSHIPS is not set", str(result.enqueue_errors[0]))
        # State should NOT have been created for the failed source
        self.assertFalse(SourceState.objects.filter(pk=INTERNSHIPS.id).exists())
        # NEW_GRAD source should have succeeded (seeding, so no outbox messages)
        self.assertTrue(SourceState.objects.filter(pk=NEW_GRAD.id).exists())

    def test_returns_failed_when_dead_lettered(self):
        self.seed()
        # Create a message at max attempts
        OutboxMessage.objects.create(
            source_id=INTERNSHIPS.id,
            webhook_env_var="DISCORD_WEBHOOK_INTERNSHIPS",
            payload={"embeds": []},
            attempt_count=MAX_DELIVERY_ATTEMPTS - 1,
        )
        http, result = self.run_with(
            {
                INTERNSHIPS.url: UNCHANGED,
                NEW_GRAD.url: UNCHANGED,
                INTERN_HOOK: FakeResponse(500, "boom"),
            }
        )
        self.assertTrue(result.failed)
        self.assertEqual(result.dead, 1)

    def test_discord_failure_leaves_message_pending_for_retry(self):
        self.seed()
        http, result = self.run_with(
            {
                INTERNSHIPS.url: listings_file("i"),
                NEW_GRAD.url: UNCHANGED,
                INTERN_HOOK: FakeResponse(500, "boom"),
            }
        )
        self.assertFalse(result.failed)  # Deferred, not dead
        msg = OutboxMessage.objects.get(source_id=INTERNSHIPS.id)
        self.assertEqual(msg.status, OutboxMessage.Status.PENDING)
        self.assertEqual(msg.attempt_count, 1)


class PostJobListingsCommandTests(TestCase):
    def setUp(self):
        logging_patcher = patch("job_postings.run.logger")
        logging_patcher.start()
        self.addCleanup(logging_patcher.stop)

    def test_exits_zero_on_success(self):
        result = RunResult(enqueue_errors=[], sent=5, deferred=0, dead=0, stale_recovered=0)
        with patch("job_postings.management.commands.post_job_listings.run", return_value=result):
            with patch.dict("os.environ", WEBHOOKS):
                call_command("post_job_listings", verbosity=0)  # Should not raise

    def test_exits_nonzero_on_enqueue_failure(self):
        result = RunResult(
            enqueue_errors=[RuntimeError("DISCORD_WEBHOOK_INTERNSHIPS is not set")],
            sent=0,
            deferred=0,
            dead=0,
            stale_recovered=0,
        )
        with patch("job_postings.management.commands.post_job_listings.run", return_value=result):
            with self.assertRaisesMessage(CommandError, "DISCORD_WEBHOOK_INTERNSHIPS is not set"):
                call_command("post_job_listings", verbosity=0)

    def test_exits_nonzero_on_dead_lettered(self):
        result = RunResult(enqueue_errors=[], sent=3, deferred=0, dead=2, stale_recovered=0)
        with patch("job_postings.management.commands.post_job_listings.run", return_value=result):
            with self.assertRaisesMessage(CommandError, "2 message(s) dead-lettered"):
                call_command("post_job_listings", verbosity=0)
