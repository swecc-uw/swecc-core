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
- If a source fails, its state is left untouched so the next run retries it. The other source still advances, and the command fails.

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
DISCORD_WEBHOOK_INTERNSHIPS=
DISCORD_WEBHOOK_NEW_GRAD=
```

A source whose webhook is not set fails without posting or touching its state.

To start over, delete the `SourceState` rows. The next run seeds silently.

## Changing sources

- To add a repo, add one entry to `SOURCES` in `sources.py` with an id, webhook variable name, raw `listings.json` URL, embed color, and a `matches` function.
- To change which categories count as software, edit `SOFTWARE_CATEGORIES` at the top of `sources.py`.
- To change the internship term year, edit `INTERNSHIP_TERM_YEAR` in the same file.
- The window and the per-source cap are `WINDOW_SECONDS` and `MAX_POSTS_PER_SOURCE` in `selection.py`.
