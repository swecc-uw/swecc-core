import math
from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass(frozen=True)
class Listing:
    id: str
    company: str
    title: str
    url: str
    locations: List[str]
    terms: List[str]
    degrees: List[str]
    category: str
    sponsorship: str
    date_posted: int
    active: bool
    visible: bool


@dataclass(frozen=True)
class Source:
    id: str
    # name of the environment variable holding the channel's webhook URL
    webhook: str
    url: str
    color: int
    matches: Callable[[Listing], bool]


SOFTWARE_CATEGORIES = {"Software", "Software Engineering"}
INTERNSHIP_TERM_YEAR = "2027"


def is_software(listing: Listing) -> bool:
    return listing.category in SOFTWARE_CATEGORIES and listing.active and listing.visible


def is_software_internship(listing: Listing) -> bool:
    return is_software(listing) and any(INTERNSHIP_TERM_YEAR in term for term in listing.terms)


SOURCES = [
    Source(
        id="simplify-internships",
        webhook="DISCORD_WEBHOOK_INTERNSHIPS",
        url="https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
        color=0x5865F2,
        matches=is_software_internship,
    ),
    Source(
        id="simplify-new-grad",
        webhook="DISCORD_WEBHOOK_NEW_GRAD",
        url="https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
        color=0x57F287,
        matches=is_software,
    ),
]


def _str(value) -> str:
    return value if isinstance(value, str) else ""


def _strs(value) -> List[str]:
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def parse_listing(raw) -> Optional[Listing]:
    if not isinstance(raw, dict):
        return None
    listing_id = _str(raw.get("id"))
    url = _str(raw.get("url"))
    date_posted = raw.get("date_posted")
    if isinstance(date_posted, bool) or not isinstance(date_posted, (int, float)):
        return None
    if not listing_id or not url or not math.isfinite(date_posted):
        return None
    return Listing(
        id=listing_id,
        company=_str(raw.get("company_name")),
        title=_str(raw.get("title")),
        url=url,
        locations=_strs(raw.get("locations")),
        terms=_strs(raw.get("terms")),
        degrees=_strs(raw.get("degrees")),
        category=_str(raw.get("category")),
        sponsorship=_str(raw.get("sponsorship")),
        date_posted=int(date_posted),
        active=raw.get("active") is True,
        visible=raw.get("is_visible") is True,
    )
