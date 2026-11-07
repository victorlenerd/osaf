"""What the rendered pages show: one business with its reviews, and the hub pages that rank
businesses by country, city and category. Built only from Afefehub's own data; nothing from
Google Places reviews or Google summaries ever reaches these structures."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.credit import credit
from app.models import Business, BusinessSummary, Review
from app.seo.slugs import (
    business_path,
    category_label,
    category_plural,
    hub_path,
    slugify,
)

# A hub is indexable (and listed in the sitemap) only with at least this many reviewed
# businesses; below it the page still renders for navigation but carries noindex.
MIN_INDEXABLE_HUB = 3
# AggregateRating is only emitted once a business has this many star-rated reviews.
MIN_RATED_FOR_AGGREGATE = 3
HUB_LIST_LIMIT = 50

COUNTRY_NAMES = {
    "NG": "Nigeria",
    "GH": "Ghana",
    "KE": "Kenya",
    "ZA": "South Africa",
    "RW": "Rwanda",
    "UG": "Uganda",
    "TZ": "Tanzania",
    "SN": "Senegal",
    "CI": "Côte d'Ivoire",
    "CM": "Cameroon",
    "ET": "Ethiopia",
    "EG": "Egypt",
    "MA": "Morocco",
    "CA": "Canada",
    "GB": "United Kingdom",
    "US": "United States",
}


def country_name(code: str | None) -> str:
    code = (code or "").upper()
    return COUNTRY_NAMES.get(code, code)


def month_year(iso: str | None) -> str:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).strftime("%B %Y")
    except ValueError:
        return ""


def human_date(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


def reviewer_name(r: Review) -> str:
    """Who the review is credited to (app/credit.py): the reviewer, or the Instagram account
    that posted a reel someone else shared."""
    c = credit(r)
    if c.name:
        return c.name
    if c.handle:
        return f"@{c.handle}"
    return "Afefehub reviewer"


def reviewer_flag_country(r: Review) -> str | None:
    """The flag is the credited reviewer's; a shared reel shows none."""
    return credit(r).country


def score(b: Business) -> float:
    """Ranking used by hubs and /api/top, published on the methodology page.

    Recommend share with a Laplace prior (one yes, one no), so one glowing review does not beat
    twenty good ones; blended 50/50 with the star average (prior of two 3-star ratings) once
    the business has star ratings."""
    counts = b.recommend_counts
    total = sum(counts.values())
    rec = (counts.get("yes", 0) + 0.5 * counts.get("maybe", 0) + 1) / (total + 2)
    if b.rating_count:
        stars = ((b.rating_sum + 3 * 2) / (b.rating_count + 2) - 1) / 4
        return 0.5 * rec + 0.5 * stars
    return rec


@dataclass
class Listing:
    business: Business
    summary: BusinessSummary | None

    @property
    def path(self) -> str:
        return business_path(self.business.slug)

    @property
    def sort_key(self) -> tuple:
        b = self.business
        # updated_at is ISO, so "newer first" is a reversed string order: negate via sort below.
        return (-score(b), -b.review_count, _neg_iso(b.updated_at), b.name.lower())


def _neg_iso(iso: str) -> tuple[int, ...]:
    return tuple(-ord(c) for c in iso)


def rank(listings: list[Listing]) -> list[Listing]:
    return sorted(listings, key=lambda li: li.sort_key)


@dataclass
class BusinessPage:
    business: Business
    summary: BusinessSummary | None
    reviews: list[Review]  # published only, newest first

    @property
    def path(self) -> str:
        return business_path(self.business.slug)

    @property
    def city_slug(self) -> str:
        return slugify(self.business.city)

    @property
    def show_aggregate(self) -> bool:
        return self.business.rating_count >= MIN_RATED_FOR_AGGREGATE

    @property
    def last_review_at(self) -> str | None:
        return self.reviews[0].created_at if self.reviews else None

    def breadcrumbs(self) -> list[tuple[str, str]]:
        """(label, path) from the site root down to this business."""
        b = self.business
        crumbs = [("Afefehub", "/"), (country_name(b.country), hub_path(b.country))]
        if self.city_slug:
            crumbs.append((b.city or "", hub_path(b.country, self.city_slug)))
            crumbs.append(
                (
                    category_label(b.category),
                    hub_path(b.country, self.city_slug, b.category),
                )
            )
        crumbs.append((b.name, self.path))
        return crumbs

    def hub_paths(self) -> list[str]:
        b = self.business
        out = ["/places", hub_path(b.country)]
        if self.city_slug:
            out += [
                hub_path(b.country, self.city_slug),
                hub_path(b.country, self.city_slug, b.category),
            ]
        return out


@dataclass
class HubLink:
    label: str
    path: str
    count: int


@dataclass
class Hub:
    path: str
    level: str  # "root" | "country" | "city" | "category"
    country: str = ""
    city: str = ""
    category: str = ""
    listings: list[Listing] = field(default_factory=list)
    children: list[HubLink] = field(default_factory=list)
    breadcrumbs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def place(self) -> str:
        if self.city:
            return f"{self.city}, {country_name(self.country)}"
        return country_name(self.country) if self.country else "Africa"

    @property
    def what(self) -> str:
        return category_plural(self.category) if self.category else "places"

    @property
    def title(self) -> str:
        if self.level == "root":
            return "Places reviewed on Afefehub, by country and city"
        return f"Best-reviewed {self.what} in {self.place}"

    @property
    def indexable(self) -> bool:
        if self.level == "root":
            return bool(self.children)
        return len(self.listings) >= MIN_INDEXABLE_HUB

    @property
    def review_total(self) -> int:
        return sum(li.business.review_count for li in self.listings)

    @property
    def updated_at(self) -> str:
        return max((li.business.updated_at for li in self.listings), default="")

    @property
    def top(self) -> list[Listing]:
        return self.listings[:HUB_LIST_LIMIT]


def build_hubs(listings: list[Listing]) -> dict[str, Hub]:
    """Every hub page, keyed by path. Cities are grouped by slug; the display name is the most
    common spelling among the businesses in that city."""
    by_country: dict[str, list[Listing]] = defaultdict(list)
    by_city: dict[tuple[str, str], list[Listing]] = defaultdict(list)
    city_names: dict[tuple[str, str], Counter] = defaultdict(Counter)
    by_cat: dict[tuple[str, str, str], list[Listing]] = defaultdict(list)

    for li in listings:
        b = li.business
        if b.review_count < 1:
            continue
        cc = (b.country or "").upper()
        if not cc:
            continue
        by_country[cc].append(li)
        cs = slugify(b.city)
        if cs:
            by_city[(cc, cs)].append(li)
            city_names[(cc, cs)][b.city or cs] += 1
            by_cat[(cc, cs, b.category)].append(li)

    hubs: dict[str, Hub] = {}
    root = Hub(path="/places", level="root", breadcrumbs=[("Afefehub", "/"), ("Places", "/places")])
    for cc, items in sorted(by_country.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        path = hub_path(cc)
        crumbs = root.breadcrumbs + [(country_name(cc), path)]
        country_hub = Hub(
            path=path, level="country", country=cc, listings=rank(items), breadcrumbs=crumbs
        )
        root.children.append(HubLink(country_name(cc), path, len(items)))
        cities = [(cs, li) for (c, cs), li in by_city.items() if c == cc]
        for cs, city_items in sorted(cities, key=lambda kv: (-len(kv[1]), kv[0])):
            city_name = city_names[(cc, cs)].most_common(1)[0][0]
            cpath = hub_path(cc, cs)
            ccrumbs = crumbs + [(city_name, cpath)]
            city_hub = Hub(
                path=cpath,
                level="city",
                country=cc,
                city=city_name,
                listings=rank(city_items),
                breadcrumbs=ccrumbs,
            )
            country_hub.children.append(HubLink(city_name, cpath, len(city_items)))
            cats = [(cat, li) for (c, s, cat), li in by_cat.items() if c == cc and s == cs]
            for cat, cat_items in sorted(cats, key=lambda kv: (-len(kv[1]), kv[0])):
                kpath = hub_path(cc, cs, cat)
                hubs[kpath] = Hub(
                    path=kpath,
                    level="category",
                    country=cc,
                    city=city_name,
                    category=cat,
                    listings=rank(cat_items),
                    breadcrumbs=ccrumbs + [(category_label(cat), kpath)],
                )
                city_hub.children.append(
                    HubLink(category_plural(cat).capitalize(), kpath, len(cat_items))
                )
            hubs[cpath] = city_hub
        hubs[path] = country_hub
    hubs[root.path] = root
    return hubs
