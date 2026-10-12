from dataclasses import replace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from .discord import build_entry, build_payloads, post_payload
from .models import SourceState
from .run import run
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


class PostPayloadTests(SimpleTestCase):
    def test_waits_out_a_rate_limit_then_retries(self):
        limited = FakeResponse(status_code=429, body={"retry_after": 0.5})
        with patch("job_postings.discord.requests.post", side_effect=[limited, ACCEPTED]) as post:
            with patch("job_postings.discord.time.sleep") as sleep:
                post_payload(INTERN_HOOK, {"embeds": []})
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_caps_retry_after_to_stay_within_gunicorn_timeout(self):
        # Discord can return retry_after up to 60s, but we cap it to avoid exceeding gunicorn's
        # 30s timeout.
        from job_postings.discord import MAX_RETRY_AFTER_SECONDS

        limited = FakeResponse(status_code=429, body={"retry_after": 60})
        with patch("job_postings.discord.requests.post", side_effect=[limited, ACCEPTED]) as post:
            with patch("job_postings.discord.time.sleep") as sleep:
                post_payload(INTERN_HOOK, {"embeds": []})
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(MAX_RETRY_AFTER_SECONDS)

    def test_gives_up_after_max_retries(self):
        from job_postings.discord import MAX_RATE_LIMIT_RETRIES

        limited = FakeResponse(status_code=429, body={"retry_after": 1})
        with patch("job_postings.discord.requests.post", return_value=limited) as post:
            with patch("job_postings.discord.time.sleep"):
                with self.assertRaisesMessage(RuntimeError, "Discord webhook failed: 429"):
                    post_payload(INTERN_HOOK, {"embeds": []})
        # Initial request + MAX_RATE_LIMIT_RETRIES retries
        self.assertEqual(post.call_count, 1 + MAX_RATE_LIMIT_RETRIES)

    def test_raises_when_discord_rejects_the_message(self):
        rejected = FakeResponse(status_code=400, body="bad embed")
        with patch("job_postings.discord.requests.post", return_value=rejected):
            with self.assertRaisesMessage(RuntimeError, "Discord webhook failed: 400 bad embed"):
                post_payload(INTERN_HOOK, {"embeds": []})


class RunTests(TestCase):
    def setUp(self):
        logging_patcher = patch("job_postings.run.logger")
        logging_patcher.start()
        self.addCleanup(logging_patcher.stop)

    def run_with(self, responses, webhooks=WEBHOOKS):
        http = FakeHttp(responses)
        with patch("job_postings.run.requests", http), patch("job_postings.discord.requests", http):
            errors = run(webhooks, NOW)
        return http, errors

    def seed(self, **seen_by_source):
        for source in SOURCES:
            SourceState.objects.create(
                source_id=source.id, etag='"v1"', seen=seen_by_source.get(source.id, {})
            )

    def state(self):
        return {s.source_id: {"etag": s.etag, "seen": s.seen} for s in SourceState.objects.all()}

    def test_seeds_on_first_run_without_posting(self):
        http, errors = self.run_with(
            {INTERNSHIPS.url: listings_file("a"), NEW_GRAD.url: listings_file("b")}
        )
        self.assertEqual([call["url"] for call in http.calls], [INTERNSHIPS.url, NEW_GRAD.url])
        self.assertEqual(errors, [])
        self.assertEqual(
            self.state(),
            {
                "simplify-internships": {"etag": '"v2"', "seen": {"a": NOW - 60}},
                "simplify-new-grad": {"etag": '"v2"', "seen": {"b": NOW - 60}},
            },
        )

    def test_posts_each_sources_new_listings_to_its_own_webhook_and_sends_if_none_match(self):
        self.seed(**{"simplify-internships": {"a": NOW - 60}})
        http, _ = self.run_with(
            {
                INTERNSHIPS.url: listings_file("a", "i"),
                NEW_GRAD.url: listings_file("g"),
                INTERN_HOOK: ACCEPTED,
                GRAD_HOOK: ACCEPTED,
            }
        )
        self.assertEqual(http.calls[0]["headers"], {"If-None-Match": '"v1"'})
        intern_posts = [call for call in http.calls if call["url"].startswith(INTERN_HOOK)]
        self.assertEqual(intern_posts[0]["url"], f"{INTERN_HOOK}?wait=true")
        self.assertEqual(len(http.descriptions(INTERN_HOOK)), 1)
        self.assertIn("https://example.com/i)", http.descriptions(INTERN_HOOK)[0])
        self.assertNotIn("https://example.com/a)", http.descriptions(INTERN_HOOK)[0])
        self.assertEqual(len(http.descriptions(GRAD_HOOK)), 1)
        self.assertIn("https://example.com/g)", http.descriptions(GRAD_HOOK)[0])
        self.assertEqual(
            self.state()["simplify-internships"],
            {"etag": '"v2"', "seen": {"a": NOW - 60, "i": NOW - 60}},
        )

    def test_leaves_the_state_untouched_when_every_source_is_unchanged(self):
        self.seed(**{"simplify-internships": {"a": NOW - 60}})
        before = self.state()
        _, errors = self.run_with({INTERNSHIPS.url: UNCHANGED, NEW_GRAD.url: UNCHANGED})
        self.assertEqual(errors, [])
        self.assertEqual(self.state(), before)

    def test_advances_the_successful_source_and_leaves_the_failed_one_as_it_was(self):
        SourceState.objects.create(source_id="simplify-new-grad", etag='"old"', seen={"z": NOW - 5})
        _, errors = self.run_with(
            {INTERNSHIPS.url: listings_file("a"), NEW_GRAD.url: FakeResponse(500, "boom")}
        )
        self.assertEqual([str(err) for err in errors], ["Fetching simplify-new-grad failed: 500"])
        self.assertEqual(
            self.state(),
            {
                "simplify-internships": {"etag": '"v2"', "seen": {"a": NOW - 60}},
                "simplify-new-grad": {"etag": '"old"', "seen": {"z": NOW - 5}},
            },
        )

    def test_marks_listings_seen_even_when_discord_fails_to_prevent_duplicates(self):
        # When Discord fails, the DB should already be updated to prevent duplicate posts on retry.
        # This is a deliberate trade-off: some listings may never be posted, but duplicates are
        # worse than missing posts.
        self.seed()
        _, errors = self.run_with(
            {
                INTERNSHIPS.url: listings_file("i"),
                NEW_GRAD.url: UNCHANGED,
                INTERN_HOOK: FakeResponse(500, "boom"),
            }
        )
        self.assertEqual([str(err) for err in errors], ["Discord webhook failed: 500 boom"])
        # The listing is marked as seen despite the Discord failure:
        self.assertEqual(
            self.state()["simplify-internships"], {"etag": '"v2"', "seen": {"i": NOW - 60}}
        )

    def test_fails_a_source_whose_webhook_is_missing_and_still_runs_the_other(self):
        self.seed()
        _, errors = self.run_with(
            {INTERNSHIPS.url: listings_file("i"), INTERN_HOOK: ACCEPTED},
            webhooks={"DISCORD_WEBHOOK_INTERNSHIPS": INTERN_HOOK},
        )
        self.assertEqual([str(err) for err in errors], ["DISCORD_WEBHOOK_NEW_GRAD is not set"])
        self.assertEqual(self.state()["simplify-internships"]["seen"], {"i": NOW - 60})
        self.assertEqual(self.state()["simplify-new-grad"], {"etag": '"v1"', "seen": {}})

    def test_gives_each_source_its_own_cap(self):
        self.seed()
        http, _ = self.run_with(
            {
                INTERNSHIPS.url: listings_file(*[f"id{n}" for n in range(30)]),
                NEW_GRAD.url: listings_file("g1", "g2"),
                INTERN_HOOK: ACCEPTED,
                GRAD_HOOK: ACCEPTED,
            }
        )
        self.assertEqual(len(self.state()["simplify-internships"]["seen"]), 30)
        self.assertEqual(len(http.descriptions(INTERN_HOOK)), 3)
        self.assertEqual(
            self.state()["simplify-new-grad"]["seen"], {"g1": NOW - 60, "g2": NOW - 60}
        )
        self.assertEqual(len(http.descriptions(GRAD_HOOK)), 1)

    def test_keeps_the_old_etag_when_the_cap_holds_listings_back(self):
        self.seed()
        self.run_with(
            {
                INTERNSHIPS.url: listings_file(*[f"id{n}" for n in range(31)]),
                NEW_GRAD.url: UNCHANGED,
                INTERN_HOOK: ACCEPTED,
            }
        )
        self.assertEqual(self.state()["simplify-internships"]["etag"], '"v1"')
        self.assertEqual(len(self.state()["simplify-internships"]["seen"]), 30)


class PostJobListingsCommandTests(SimpleTestCase):
    def test_passes_the_environment_to_the_run(self):
        with patch("job_postings.management.commands.post_job_listings.run", return_value=[]) as r:
            with patch.dict("os.environ", WEBHOOKS):
                call_command("post_job_listings", verbosity=0)
                self.assertEqual(r.call_args[0][0]["DISCORD_WEBHOOK_NEW_GRAD"], GRAD_HOOK)

    def test_fails_when_a_source_failed(self):
        errors = [RuntimeError("DISCORD_WEBHOOK_NEW_GRAD is not set")]
        with patch("job_postings.management.commands.post_job_listings.run", return_value=errors):
            with self.assertRaisesMessage(CommandError, "DISCORD_WEBHOOK_NEW_GRAD is not set"):
                call_command("post_job_listings", verbosity=0)
