from typing import Dict, List, Optional, Tuple

from .sources import Listing, Source

WINDOW_SECONDS = 3 * 24 * 60 * 60
MAX_POSTS_PER_SOURCE = 30


def select_new(
    listings: List[Listing], source: Source, prev_seen: Optional[Dict[str, int]], now: int
) -> Tuple[List[Listing], Dict[str, int], bool]:
    """Returns (fresh, seen, deferred). `prev_seen` is None on a source's first run."""
    cutoff = now - WINDOW_SECONDS
    candidates = sorted(
        (
            listing
            for listing in listings
            if source.matches(listing) and listing.date_posted >= cutoff
        ),
        key=lambda listing: listing.date_posted,
    )

    seen = {
        listing_id: posted for listing_id, posted in (prev_seen or {}).items() if posted >= cutoff
    }

    if prev_seen is None:
        for listing in candidates:
            seen[listing.id] = listing.date_posted
        return [], seen, False

    unseen = [listing for listing in candidates if listing.id not in seen]
    fresh = unseen[:MAX_POSTS_PER_SOURCE]
    for listing in fresh:
        seen[listing.id] = listing.date_posted
    return fresh, seen, len(fresh) < len(unseen)
