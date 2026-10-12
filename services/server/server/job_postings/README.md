# job_postings

> ## Credit: all listings come from [Simplify](https://simplify.jobs)
>
> Simplify and its community of contributors find, verify and maintain every listing this posts, in two open repositories:
>
> - [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships)
> - [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions)

The `post_job_listings` management command checks the SimplifyJobs listing files on GitHub and posts newly added software internship (2027 terms) and new grad listings to Discord. Internships and new grad roles each go to their own channel webhook.

Each run has two steps. It first works out which listings are new and queues one Discord message per batch of them. It then sends queued messages, including any left over from earlier runs.

## How it decides what is new

- Each source is fetched with `If-None-Match`. A 304 response skips the source.
- A listing is a candidate when it matches the source filter and was posted within the last 3 days.
- The first run for a source is a seed run. It queues nothing and records every candidate id as seen.
- Later runs queue candidates whose id is not in the seen set, oldest first, at most 30 per source per run. Candidates over the cap are not marked seen and are queued on the next run.
- Listings are grouped into messages of up to 10, so a source queues at most 3 messages per run.
- Seen ids older than 3 days are dropped, so state stays small.
- If a source fails, its state is left untouched and nothing is queued for it, so the next run retries it. The other source still advances.

Marking listings as seen and queueing their messages happen in one transaction. A listing is never marked seen without a message queued for it.

## How messages are sent

Queued messages live in the `OutboxMessage` table. Each run sends the ones that are due, oldest first, across both sources:

1. Claim the message: set its status to `sending` and record `claimed_at`.
2. Post it to Discord, outside any database transaction.
3. Record the outcome: `sent`, or back to `pending` with a time for the next attempt.

A run sends at most 5 messages and stops claiming new ones 20 seconds after sending starts. The rest wait for the next run. These limits exist because the scheduler triggers the command through a gunicorn request, which is cut off after 30 seconds. The 20 seconds do not include the time spent fetching the listing files first.

What happens when a send does not succeed:

| Outcome | What happens to the message |
| --- | --- |
| Discord returns 429 | Back to `pending`, due again after Discord's `retry_after`. Counts as an attempt. |
| Any other error, including a network failure | Back to `pending` with a backoff of 1, 2, 4, 8, 16 and 32 minutes, then 60 minutes. Counts as an attempt. |
| 10th failed attempt | Marked `dead` and never retried on its own. |
| The message's webhook variable is no longer set | Stays `pending` and is due again in 30 minutes. Does not count as an attempt. The run stops sending at that point, so messages behind it wait for the next run. |
| The run dies between claiming and recording the outcome | Stays `sending`. A run that starts more than 3 minutes later puts it back to `pending`. |

Two consequences:

- **A message can be posted twice.** Discord webhooks have no idempotency key, so when a run dies after Discord accepted a message but before that was recorded, the message is sent again. This is rare, and it was chosen over dropping listings.
- **Messages can arrive out of order.** A message that is waiting to be retried does not hold back the newer ones behind it.

## How it runs

`services/scheduler/schedule/tasks.sh` calls the command through `POST /admin/command/` at :08 and :38 of every hour (UTC), a few minutes after upstream's half-hourly update. A run with no new listings and nothing due in the queue posts nothing.

State is in two tables:

- `SourceState` has one row per source, holding the source's etag and the seen listing ids. A source's row is locked while its listings are checked, so overlapping runs queue instead of racing.
- `OutboxMessage` has one row per Discord message, with its status, attempt count, next attempt time and last error. Rows are kept after they are sent.

To run it by hand:

```
python manage.py post_job_listings
```

A manual run does exactly what a scheduled run does, including posting to Discord.

## Setup

Set the two webhook URLs in the server's environment:

```
DISCORD_WEBHOOK_INTERNSHIPS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_NEW_GRAD=https://discord.com/api/webhooks/...
```

A source's webhook is checked before anything else. If it is not set, the source fails without being seeded, marked seen or queued, and the command fails.

To start over, delete the `SourceState` rows and any `OutboxMessage` rows that are not `sent`. The next run seeds silently.

## What the command reports

The command prints how many messages were sent, deferred and dead-lettered, and how many stale `sending` messages were put back to `pending`.

It fails when either of these happened during the run:

- A source could not be checked, for example a fetch error or a missing webhook.
- A message reached its 10th failed attempt and was marked `dead`.

A message that died in an earlier run does not fail later runs. Deferred messages do not fail a run either, so a successful run can still leave messages waiting in the queue.

## Checking the queue

In `python manage.py shell`:

```python
from datetime import timedelta

from django.utils import timezone
from job_postings.models import OutboxMessage

# Counts by status
for status in OutboxMessage.Status:
    print(status.label, OutboxMessage.objects.filter(status=status).count())

# Messages that gave up, and why
for msg in OutboxMessage.objects.filter(status="dead"):
    print(msg.id, msg.source_id, msg.attempt_count, msg.last_error)

# Messages stuck in sending, which the next run will put back to pending
print(
    OutboxMessage.objects.filter(
        status="sending", claimed_at__lt=timezone.now() - timedelta(minutes=3)
    ).count()
)
```

## Replaying dead messages

Reset the messages to `pending`, then run the command or wait for the next scheduled run:

```python
from job_postings.models import OutboxMessage

OutboxMessage.objects.filter(id__in=[1, 2, 3]).update(
    status="pending",
    attempt_count=0,
    next_attempt_at=None,
    last_error="Manually reset for replay",
)
```

Use `filter(status="dead")` instead to replay all of them.

## Changing sources and limits

- To add a repo, add one entry to `SOURCES` in `sources.py` with an id, webhook variable name, raw `listings.json` URL, embed color, and a `matches` function.
- To change which categories count as software, edit `SOFTWARE_CATEGORIES` at the top of `sources.py`.
- To change the internship term year, edit `INTERNSHIP_TERM_YEAR` in the same file.
- The window and the per-source cap are `WINDOW_SECONDS` and `MAX_POSTS_PER_SOURCE` in `selection.py`.
- The sending limits are at the top of `run.py`: `MAX_MESSAGES_PER_RUN`, `RUN_DEADLINE_SECONDS`, `MAX_DELIVERY_ATTEMPTS` and `LEASE_TIMEOUT_SECONDS`.
