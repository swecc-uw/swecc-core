# job_postings

> ## Credit: all listings come from [Simplify](https://simplify.jobs)
>
> Simplify and its community of contributors find, verify and maintain every listing this posts, in two open repositories:
>
> - [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships)
> - [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions)

The `post_job_listings` management command checks the SimplifyJobs listing files on GitHub and posts newly added software internship (2027 terms) and new grad listings to Discord. Internships and new grad roles each go to their own channel webhook.

## How it decides what is new

- Each source is fetched with `If-None-Match`. A 304 response skips the source.
- A listing is a candidate when it matches the source filter and was posted within the last 3 days.
- The first run for a source is a seed run. It posts nothing and records every candidate id as seen.
- Later runs post candidates whose id is not in the seen set, oldest first, at most 30 per source per run. Candidates over the cap are not marked seen and post on the next run.
- Seen ids older than 3 days are dropped, so state stays small.
- If a source fails, its state is left untouched so the next run retries it.

## How it runs

`services/scheduler/schedule/tasks.sh` calls the command through `POST /admin/command/` at :08 and :38 of every hour (UTC), a few minutes after upstream's half-hourly update. A run that finds nothing new posts nothing.

State is one `SourceState` row per source, holding the source's etag and the seen listing ids. Each source runs in its own transaction with its row locked, so overlapping runs queue instead of racing.

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

**Important:** Webhook configuration is validated before any state is modified. If a webhook is missing, the source fails fast without seeding or enqueueing messages. This prevents silent failures where listings are marked as seen but never posted.

To start over, delete the `SourceState` rows. The next run seeds silently.

## Delivery semantics

### At-least-once delivery

Discord webhooks have no idempotency key, so this system uses **at-least-once delivery semantics**. In rare cases (worker crash during send), a message may be posted to Discord more than once. This is preferred over silent drops.

The delivery flow:
1. **Claim:** Set message status to `sending` with a `claimed_at` timestamp (short transaction)
2. **Send:** Make the Discord API call **outside any transaction**
3. **Complete:** Update status to `sent` or back to `pending` with backoff (short transaction)

If a worker crashes between claim and complete, the message stays in `sending` status. After 3 minutes (the lease timeout), a subsequent run re-queues it as `pending` and logs a warning. This may cause a duplicate post if the original send succeeded before the crash.

### Per-run limits

To stay within the 30-second gunicorn timeout:
- **Max 5 messages per run** - additional messages wait for the next run
- **20-second deadline** - stop claiming new messages after this time

### Failure handling

- **Rate limited (429):** Message is deferred with Discord's `retry_after` value
- **Other errors:** Exponential backoff (1min, 2min, 4min... up to 60min)
- **Dead-lettered:** After 10 failed attempts, message is marked `dead` and stops retrying
- **Missing webhook config:** Message stays `pending` without counting as an attempt; it will be delivered once the config is restored

## Failure reporting and exit codes

The command exits nonzero (failure) when:
- Any source fails to enqueue (e.g., fetch error, missing webhook config)
- Any message is dead-lettered

The exit message includes:
- Enqueue error details
- Count of dead-lettered messages

A zero exit means all sources were processed and no messages were dead-lettered (though some may be deferred for retry).

## Replaying dead messages

Dead-lettered messages (`status='dead'`) have given up after 10 attempts. To replay them:

```python
# In Django shell: python manage.py shell

from job_postings.models import OutboxMessage

# View dead messages
dead = OutboxMessage.objects.filter(status='dead')
for msg in dead:
    print(f"ID {msg.id}: {msg.source_id}, attempts={msg.attempt_count}, error={msg.last_error}")

# Reset specific messages to retry
OutboxMessage.objects.filter(id__in=[1, 2, 3]).update(
    status='pending',
    attempt_count=0,
    next_attempt_at=None,
    last_error='Manually reset for replay',
)

# Reset all dead messages (use with caution)
OutboxMessage.objects.filter(status='dead').update(
    status='pending',
    attempt_count=0,
    next_attempt_at=None,
    last_error='Manually reset for replay',
)
```

Then run `python manage.py post_job_listings` to attempt delivery.

## Monitoring

Check the outbox status:

```python
from job_postings.models import OutboxMessage

# Counts by status
for status in OutboxMessage.Status:
    count = OutboxMessage.objects.filter(status=status).count()
    print(f"{status.label}: {count}")

# Stuck in sending (possible stale leases)
from django.utils import timezone
from datetime import timedelta
stale = OutboxMessage.objects.filter(
    status='sending',
    claimed_at__lt=timezone.now() - timedelta(minutes=3)
)
print(f"Stale leases: {stale.count()}")
```

## Changing sources

- To add a repo, add one entry to `SOURCES` in `sources.py` with an id, webhook variable name, raw `listings.json` URL, embed color, and a `matches` function.
- To change which categories count as software, edit `SOFTWARE_CATEGORIES` at the top of `sources.py`.
- To change the internship term year, edit `INTERNSHIP_TERM_YEAR` in the same file.
- The window and the per-source cap are `WINDOW_SECONDS` and `MAX_POSTS_PER_SOURCE` in `selection.py`.
