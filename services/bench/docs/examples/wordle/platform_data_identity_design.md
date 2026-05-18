# BenchAnything Data and Identity Design

**Status:** Draft
**Date:** April 22, 2026
**Author:** Codex

## Problem Statement

BenchAnything's current storage model is good enough for a local MVP, but it will become a bottleneck as soon as we have real users, many runs, and multi-turn traces. Today, core entities such as `domains`, `runs`, and `episodes` are stored as opaque JSON blobs in SQLite, while trace events are written as one JSONL file per episode under `./data/traces`. That makes writes easy, but it makes product questions and operational questions hard: "show me failed runs for one user over the last week", "filter only tool calls from this episode", "rank runs by metric without reparsing blobs", and "who owns this draft domain?" all require application-side scans or ad hoc conventions.

At the same time, the API already models ownership with free-form string fields like `owner_id` and `requester_id`, but there is no real user identity, no authentication, and no authorization boundary. That prevents us from safely shipping user-specific experiences such as personal dashboards, saved runs, or draft/private resources.

This document proposes a pragmatic next version of the data model: keep local development simple, but move production toward a normalized relational schema with append-only event storage, derived metrics, and minimal Google-based identity restricted to UW accounts.

## Glossary

**Domain** is a benchmark or environment definition registered with the platform.
**Domain Version** is an immutable snapshot of a domain's binding vow, scoring, and endpoint metadata at publish time.
**Run** is a benchmark execution request over one domain version and one agent configuration.
**Episode** is a single seeded execution inside a run.
**Trace Event** is one append-only event emitted during an episode, such as an observation, action, model call, or terminal result.
**User** is an authenticated person in BenchAnything. In this proposal, all users authenticate with Google and must belong to the UW domain.
**Session** is the server-side login state associated with an authenticated user.

## Current State

The current implementation has three useful properties: it is easy to understand, easy to serialize from Pydantic, and fast enough for a handful of local runs. It also has four structural weaknesses.

First, important query dimensions are trapped inside JSON text. For example, `RunRow` stores only `id`, `domain_id`, `status`, and a `data` blob, even though the product will routinely want to filter by requester, model, binding vow version, timestamps, and scores. `EpisodeRow` has the same problem. This leads to repeated JSON parsing in Python and prevents the database from doing efficient filtering or aggregation.

Second, trace access is file-oriented instead of query-oriented. The `/v1/runs/{run_id}/traces` route reads every episode file in full and returns every event, and the WebSocket tailer repeatedly rereads the whole file to find newly appended events. That is acceptable for short text-only traces, but it will break down for long-horizon agent runs, multimodal payloads, and concurrent viewers.

Third, some tables are redundant or under-defined. `leaderboard` partially duplicates information already derivable from runs and scores, while `environment_usage` exists as a table even though usage is recomputed from runs and leaderboard rows in the current code. The schema has very few foreign keys, very few typed timestamps, and no durable notion of tenancy.

Fourth, the system is not ready for user-specific behavior. A client can currently send any `owner_id` or `requester_id` string. That is fine for a toy server, but not for a shared UW deployment.

## Use Cases

The storage and identity changes should directly enable user-visible workflows.

A UW student signs in with Google, lands on a personal dashboard, and sees their draft domains, submitted developer environments, and their most recent runs without passing an `owner_id` manually.

A researcher opens a run detail page, filters trace events to only `tool_call` and `model_call`, jumps to step 73, and paginates forward without loading the entire episode file into memory.

A course staff member compares all runs they launched on a domain version over the last seven days, grouped by model and benchmark technique, and exports those metrics without reparsing JSON blobs.

A user bookmarks a few runs and domains into a saved workspace so they can revisit experiments later and compare outcomes across model versions.

## Breaking Changes

This proposal intentionally changes some API behavior.

Mutating endpoints will stop accepting caller-supplied `owner_id` and `requester_id`. The backend will derive those values from the authenticated session.

Trace retrieval will become paginated and filterable instead of returning "all events for all episodes" by default.

Published benchmark metadata will move from a single mutable `domains` record to a mutable draft plus immutable `domain_versions`.

For production deployments, PostgreSQL becomes the primary database. SQLite remains supported for local development and tests.

## Success Criteria

We should treat this work as successful if, within one release after rollout, the following are true.

The platform can answer common dashboard queries from SQL alone without reparsing JSON blobs in application code.

The first page of trace events for a large run returns in under 500 ms at p95, and filtered trace queries by `event_type` or `episode_id` return in under 300 ms at p95 in production.

One hundred percent of created domains, runs, and developer environments are linked to an authenticated user record rather than a free-form string.

One hundred percent of successful sign-ins come from Google-issued tokens whose `sub` identifies the account and whose hosted domain is accepted as UW.

At least two user-specific flows are shipped: a personal dashboard and saved run/domain collections.

## Proposed Design

The core idea is to split platform data into three layers.

The first layer is **control-plane metadata**: users, sessions, domains, domain versions, runs, and episodes. These tables should be normalized, strongly keyed, and optimized for product queries.

The second layer is **append-only execution data**: trace events, model calls, tool calls, and artifact references. This layer is write-heavy and query-heavy, and it should be optimized for pagination, filtering, and replay rather than full-document updates.

The third layer is **derived analytics**: run metrics, leaderboard views, and daily usage rollups. These are computed from the first two layers and exist to make the product fast.

This shape matches the direction of modern RL systems. The open-source RL stacks that are strongest in multi-turn settings increasingly treat rollout data as a first-class data model rather than a miscellaneous log. NeMo-RL emphasizes explicit trajectory representations, SkyRL separates generation and training concerns, and slime centralizes prompt and rollout buffering. BenchAnything is not a trainer, but it has the same architectural pressure: long-lived, append-only, multi-step trajectories should not live only inside opaque files and JSON blobs.

## Technical Design

### Database Choice

We should keep SQLite for local development because it lowers setup cost and fits the repo today. For any shared deployment, we should use PostgreSQL. The reasons are straightforward: typed timestamps, JSONB, stronger indexing, better concurrent access patterns, and a much better path for large append-only event tables.

The application code can still use SQLAlchemy and hide most dialect differences. We do not need to make local development harder to get a production-capable schema.

### Core Tables

Below is the recommended logical schema. JSON is still allowed, but only for flexible leaf data, not for the fields we know we will query constantly.

```sql
users (
  id uuid primary key,
  google_sub text unique not null,
  email text unique not null,
  email_domain text not null,
  display_name text not null,
  picture_url text,
  auth_provider text not null default 'google',
  status text not null default 'active',
  created_at timestamptz not null,
  last_login_at timestamptz
)

user_sessions (
  id uuid primary key,
  user_id uuid not null references users(id),
  session_token_hash text unique not null,
  expires_at timestamptz not null,
  created_at timestamptz not null,
  revoked_at timestamptz
)

domains (
  id text primary key,
  owner_user_id uuid not null references users(id),
  current_draft_version_id uuid,
  latest_published_version_id uuid,
  slug text unique not null,
  name text not null,
  status text not null,
  visibility text not null default 'private',
  created_at timestamptz not null,
  updated_at timestamptz not null,
  published_at timestamptz
)

domain_versions (
  id uuid primary key,
  domain_id text not null references domains(id),
  version text not null,
  binding_vow jsonb not null,
  scoring_config jsonb not null,
  endpoint_config jsonb not null,
  tags text[] not null default '{}',
  detail text not null default '',
  created_by_user_id uuid not null references users(id),
  created_at timestamptz not null,
  unique(domain_id, version)
)

runs (
  id uuid primary key,
  domain_id text not null references domains(id),
  domain_version_id uuid not null references domain_versions(id),
  requester_user_id uuid not null references users(id),
  status text not null,
  model text not null,
  technique_config jsonb not null default '[]',
  system_prompt text,
  temperature double precision not null,
  max_tokens integer not null,
  num_episodes integer not null,
  max_parallel integer not null,
  created_at timestamptz not null,
  started_at timestamptz,
  completed_at timestamptz,
  primary_score double precision,
  score_summary jsonb not null default '{}'
)

episodes (
  id uuid primary key,
  run_id uuid not null references runs(id),
  seed integer,
  status text not null,
  started_at timestamptz,
  ended_at timestamptz,
  steps integer not null default 0,
  total_reward double precision not null default 0,
  terminal_reason text,
  terminal_info jsonb not null default '{}'
)

trace_events (
  id bigserial primary key,
  run_id uuid not null references runs(id),
  episode_id uuid not null references episodes(id),
  seq_no bigint not null,
  step integer not null,
  event_type text not null,
  ts timestamptz not null,
  model text,
  tool_name text,
  latency_ms integer,
  token_in integer,
  token_out integer,
  payload jsonb not null default '{}',
  blob_ref text,
  unique(episode_id, seq_no)
)

run_metrics (
  run_id uuid not null references runs(id),
  metric_name text not null,
  metric_value double precision not null,
  primary key (run_id, metric_name)
)

saved_entities (
  id uuid primary key,
  user_id uuid not null references users(id),
  entity_type text not null,
  entity_id text not null,
  note text not null default '',
  created_at timestamptz not null,
  unique(user_id, entity_type, entity_id)
)
```

### Indexes

The minimum useful indexes are:

`runs (requester_user_id, created_at desc)` for the dashboard.
`runs (domain_id, status, created_at desc)` for domain history.
`runs (domain_version_id, model, created_at desc)` for comparisons.
`episodes (run_id, status, started_at desc)` for run detail pages.
`trace_events (episode_id, seq_no)` for replay and pagination.
`trace_events (run_id, event_type, ts)` for filtered log queries.
`run_metrics (metric_name, metric_value desc)` to support leaderboard materialization.

If production volume grows substantially, `trace_events` should be partitioned by month or by `run_id` hash, but that can wait until after we have real data.

### What Stays as JSON

Three things should remain flexible.

The binding vow, scoring config, and endpoint config should stay as JSON because they are semi-structured contracts that will evolve.

Trace event payloads should stay as JSON because different event types carry different shapes.

Large artifacts such as screenshots, HTML dumps, or multimodal attachments should not be inlined into the database. The event row should store metadata plus a `blob_ref` pointing at object storage or the local filesystem in development.

### Trace Storage Model

Today, `TraceStore.append()` writes one JSON line per event. That append-only contract is good and we should preserve it. The change is that the append path should dual-write: one lightweight structured event row for queries, and one optional raw artifact for large payloads.

This keeps the "event log" nature of the current design while making it queryable. It also gives us a path to future asynchronous consumers, such as offline replay export, training-data extraction, or live dashboards.

The route surface should change from:

`GET /v1/runs/{run_id}/traces`

to something closer to:

`GET /v1/runs/{run_id}/trace-events?episode_id=...&event_type=tool_call&cursor=...&limit=200`

That API is both cheaper and more future-proof.

### Leaderboards and Usage

`leaderboard` should become a view or materialized table backed by `runs`, `run_metrics`, and `domain_versions`. We should not maintain a bespoke source of truth unless we have a write-path reason to do so.

`environment_usage` should also become derived data. A daily rollup table such as `domain_usage_daily` is defensible if the dashboard gets slow, but the current standalone table is not adding much value.

## Identity and Authentication

### Login Flow

BenchAnything should support only Google sign-in for now, and only for UW accounts.

The frontend uses Google Identity Services and sends the Google ID token to `POST /v1/auth/google`. The backend verifies the token with a Google library, validates `aud`, `iss`, `exp`, and then checks that the token represents an accepted hosted domain. Google recommends using the token's `sub` as the durable identifier and checking the `hd` claim when domain membership matters; the email string alone is not a safe primary identifier.

On successful verification, the backend upserts a `users` row keyed by `google_sub`, updates profile fields such as `email`, `display_name`, and `picture_url`, and creates a `user_sessions` row. The client receives an opaque session cookie marked `HttpOnly`, `Secure`, and `SameSite=Lax`.

### UW Restriction

The MVP should accept an allowlist of hosted domains, with initial value `["uw.edu"]`. A token is accepted only if:

the Google signature and audience checks pass,
`email_verified` is true,
`hd` is present and equals an allowed UW domain, and
the normalized email suffix matches the same allowlist.

Checking both `hd` and suffix protects the product requirement clearly and avoids relying on an editable client-side login hint.

### Authorization Model

Authorization can stay simple in MVP.

Any signed-in UW user can view published domains and public leaderboards.

Only the owning user can update or publish a draft domain.

Only the requesting user can see private run details, saved entities, and draft resources associated with them.

Admin roles are out of scope for the first pass.

## User-Specific Features

### Feature 1: My BenchAnything Dashboard

Every authenticated user gets a dashboard at `/v1/me/dashboard` showing:

their recent runs,
their draft and published domains,
their developer environment submissions, and
their saved entities.

This is the first place users will feel the identity model. It also forces the backend to answer the right queries efficiently, which is exactly why the schema needs to change.

### Feature 2: Saved Runs and Domains

Users can bookmark a run or a domain for later reference, optionally with a short note. This is implemented by `saved_entities`, not by denormalizing lists onto the user record.

This feature is low-risk, obviously useful for researchers, and creates a durable user-specific surface without requiring collaboration, notifications, or a large permission system.

### Feature 3: Private Draft Ownership

Draft domains and in-progress developer environments should be private to the owning user by default. The current product shape already distinguishes drafts from published domains; this feature simply makes that distinction real through authentication and authorization.

Even if we ship only the first two features in the first milestone, private draft ownership should be considered part of the identity MVP rather than a future add-on.

## Components

The browser handles sign-in and session bootstrap.

The FastAPI API layer validates sessions, resolves the current user, and removes caller-controlled ownership fields from write APIs.

The orchestrator creates runs and episodes with user-linked metadata.

The trace ingestion path writes append-only execution events into queryable storage and optionally emits large artifacts to blob storage.

The dashboard and leaderboard read mostly from normalized metadata and derived metric tables rather than reparsing blobs.

## New APIs and Behaviors

The minimum new endpoints are:

`POST /v1/auth/google` to exchange a Google ID token for a session.
`POST /v1/auth/logout` to revoke the current session.
`GET /v1/me` to return the signed-in user.
`GET /v1/me/dashboard` to return user-centric summary data.
`POST /v1/saved-entities` and `DELETE /v1/saved-entities/{id}` for bookmarks.
`GET /v1/runs/{run_id}/trace-events` for paginated event access.

The existing `create_domain`, `submit_environment`, and `create_run` flows should stop taking owner identity in the request body. The backend should fill it from the session.

## Monitoring

We should add at least the following technical metrics:

auth success rate, auth rejection rate, and reasons for rejection,
trace event insert latency and throughput,
trace query p50 and p95 latency by endpoint,
run creation to first event latency, and
dashboard query latency.

We should also track the ratio of trace events with external `blob_ref` attachments so we know when multimodal storage pressure starts to matter.

## Pros and Cons

The main advantage of this design is that it matches the product we are trying to build. BenchAnything is a multi-turn evaluation system. Treating runs and traces as first-class relational data makes querying, authorization, analytics, and user experiences much simpler.

The main downside is complexity. The current code benefits from almost no migration burden. Moving to normalized tables, sessions, and event ingestion adds schema management, auth edge cases, and more operational moving pieces.

That tradeoff is worth it because the existing shape will otherwise force us to build product features in increasingly expensive application code.

## Major Risks and Mitigations

The largest technical risk is overbuilding before we have enough data. The mitigation is to keep SQLite for local work, keep JSON where flexibility matters, and roll out the normalized schema in stages rather than requiring an all-at-once rewrite.

The largest product risk is auth friction for users who have Google accounts but not the exact UW domain we allow. The mitigation is to make the allowlist configurable while shipping `uw.edu` only in MVP.

The largest migration risk is dual-writing traces incorrectly. The mitigation is to preserve the append-only contract, add sequence numbers per episode, and backfill old JSONL traces with an idempotent migration script.

## Security

The backend must verify Google ID tokens server-side and must store the stable Google `sub` as the user's external identity. It should not trust client-supplied email or user IDs.

Sessions should be opaque, revocable, and stored hashed at rest. Cookies should be `HttpOnly`, `Secure`, and `SameSite=Lax`.

Published domains remain public, but draft assets, private runs, and saved entities must require authentication.

## Migration Plan

This should be rolled out in four stages rather than as a flag day.

In stage 1, add the new normalized tables and begin writing new rows for users, sessions, runs, episodes, and trace events while leaving the current blob-backed reads intact.

In stage 2, switch dashboard, leaderboard, and trace APIs to read from the new schema. During this stage, `TraceStore` can continue to emit JSONL for local replay or debugging, but the database becomes the source for product queries.

In stage 3, backfill historical runs and episodes from the blob rows, and backfill any existing JSONL traces into `trace_events` with deterministic `seq_no` ordering.

In stage 4, remove write dependencies on blob-backed `data` columns for the hot path. We can keep full JSON snapshots around temporarily for rollback safety, but they should stop being the primary operational store.

## Scope

The first implementation milestone includes:

normalized `users`, `user_sessions`, `domains`, `domain_versions`, `runs`, `episodes`, `trace_events`, and `saved_entities` tables,
Google sign-in restricted to UW accounts,
dashboard queries for the signed-in user,
saved runs/domains, and
paginated trace-event queries.

## Out of Scope

GitHub auth, password auth, and non-UW accounts are out of scope.

Collaboration roles, shared projects, and notifications are out of scope.

Full object storage migration for every artifact is out of scope if traces remain text-only in the short term.

Realtime push-based trace streaming can stay on the current WebSocket model for now, as long as the underlying read path uses indexed event queries.

## Alternatives Considered

### Alternative 1: Keep the Current JSON Blob Model

This would be the cheapest short-term option and would avoid migration work.

It was rejected because it makes the next wave of product work harder in exactly the places we care about: filtering traces, attributing data to users, and building dashboards without reparsing blobs.

### Alternative 2: Put All Trace Data in an External Search System

We could send logs directly to something like OpenSearch or ClickHouse and keep the relational database small.

This is attractive eventually, but it is too much operational surface area for the current stage. We should first get the relational event model right, then decide later whether a specialized log store is warranted.

## Open Questions

Should published domains be public to anyone on the internet, or only to signed-in UW users?

Do we expect multiple accepted UW-affiliated domains soon, such as departmental subdomains, or is `uw.edu` truly sufficient for the first semester?

Do we want draft domain sharing in the second milestone, and if so should we introduce a general ACL table now or wait?

## Appendix

This proposal follows the spirit of Eric Clemmons' "Write Design Docs like Amazon": clear problem statement, explicit use cases, measurable success criteria, and direct treatment of breaking changes, risks, and alternatives.

Two source inputs especially shaped the design.

The current repository implementation, especially `src/storage/models.py`, `src/storage/database.py`, `src/storage/trace_store.py`, and the run/leaderboard routes, shows that metadata is currently split between SQLite blob rows and JSONL trace files.

The July 1, 2025 "Open Source RL Libraries for LLMs" comparison argues, across several frameworks, that multi-turn RL systems increasingly benefit from explicit rollout and environment abstractions. That is a useful prior for BenchAnything because our logs are not incidental debug output; they are part of the product and should be modeled as such.
