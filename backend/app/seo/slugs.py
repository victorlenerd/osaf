"""Stable, readable URLs for the server-rendered pages.

A business page lives at /b/<name>-<city>-<hash6>. The hash comes from the business id, so two
businesses with the same name in the same city never collide, and the slug never changes as
long as the stored name and city do not (both are set once, on first publish).

Hub pages live at /places/<cc>, /places/<cc>/<city> and /places/<cc>/<city>/<category>.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
MAX_PART = 48

# URL segment and plural label per category, for hub pages ("best restaurants in Lagos").
CATEGORY_PATHS: dict[str, tuple[str, str]] = {
    "restaurant": ("restaurants", "restaurants"),
    "street_food": ("street-food", "street food spots"),
    "cafe": ("cafes", "cafés"),
    "bar_lounge": ("bars-and-lounges", "bars and lounges"),
    "hotel": ("hotels", "hotels"),
    "salon_barber": ("salons-and-barbers", "salons and barbers"),
    "spa_wellness": ("spas-and-wellness", "spas and wellness centres"),
    "retail": ("shops", "shops"),
    "supermarket": ("supermarkets", "supermarkets"),
    "fashion": ("fashion", "fashion stores"),
    "electronics": ("electronics", "electronics stores"),
    "auto": ("auto-services", "auto services"),
    "health_clinic": ("clinics", "clinics"),
    "pharmacy": ("pharmacies", "pharmacies"),
    "education": ("schools-and-education", "schools and education centres"),
    "events_venue": ("event-venues", "event venues"),
    "transport": ("transport", "transport services"),
    "real_estate": ("real-estate", "real estate agents"),
    "services": ("services", "service providers"),
    "other": ("other-places", "other places"),
}

CATEGORY_LABELS: dict[str, str] = {
    "restaurant": "Restaurant",
    "street_food": "Street food",
    "cafe": "Café",
    "bar_lounge": "Bar & lounge",
    "hotel": "Hotel",
    "salon_barber": "Salon & barber",
    "spa_wellness": "Spa & wellness",
    "retail": "Retail",
    "supermarket": "Supermarket",
    "fashion": "Fashion",
    "electronics": "Electronics",
    "auto": "Auto",
    "health_clinic": "Health clinic",
    "pharmacy": "Pharmacy",
    "education": "Education",
    "events_venue": "Events venue",
    "transport": "Transport",
    "real_estate": "Real estate",
    "services": "Services",
    "other": "Other",
}


DEMO_PREFIX = "afefe:demo-"


def is_demo(business_id: str) -> bool:
    """Fictional seed businesses (scripts/seed_demo.py). Never rendered as crawlable pages, put
    in structured data or sitemaps, or returned to AI agents: their reviews are not real."""
    return business_id.startswith(DEMO_PREFIX)


def slugify(s: str | None, max_len: int = MAX_PART) -> str:
    """ASCII, lowercase, hyphen-separated: "Café Néo — Lekki" -> "cafe-neo-lekki"."""
    if not s:
        return ""
    folded = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    out = _NON_ALNUM.sub("-", folded.lower()).strip("-")
    if len(out) > max_len:
        out = out[:max_len].rsplit("-", 1)[0] or out[:max_len]
    return out


def id_hash(business_id: str) -> str:
    return hashlib.sha1(business_id.encode("utf-8")).hexdigest()[:6]


def business_slug(business_id: str, name: str, city: str | None) -> str:
    name_part = slugify(name) or "business"
    city_part = slugify(city)
    parts = [name_part]
    if city_part and not name_part.endswith(city_part):
        parts.append(city_part)
    parts.append(id_hash(business_id))
    return "-".join(parts)


def business_path(slug: str) -> str:
    return f"/b/{slug}"


def category_segment(category: str) -> str:
    return CATEGORY_PATHS.get(category, (slugify(category), category))[0]


def category_plural(category: str) -> str:
    return CATEGORY_PATHS.get(category, ("", category.replace("_", " ")))[1]


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


def hub_path(country: str, city_slug: str | None = None, category: str | None = None) -> str:
    """/places/ng, /places/ng/lagos, /places/ng/lagos/restaurants. No trailing slash."""
    parts = ["/places", country.lower()]
    if city_slug:
        parts.append(city_slug)
        if category:
            parts.append(category_segment(category))
    return "/".join(parts)
