"""schema.org JSON-LD for the rendered pages.

Only Afefehub's own reviews and summaries are described. Star ratings appear only where a
reviewer gave one, and AggregateRating only once enough reviews are rated (see model.py)."""

from __future__ import annotations

import json

from app.config import get_settings
from app.seo.model import BusinessPage, Hub, country_name, reviewer_name

# Afefehub category -> the most specific schema.org LocalBusiness subtype.
SCHEMA_TYPES: dict[str, str] = {
    "restaurant": "Restaurant",
    "street_food": "Restaurant",
    "cafe": "CafeOrCoffeeShop",
    "bar_lounge": "BarOrPub",
    "hotel": "Hotel",
    "salon_barber": "HairSalon",
    "spa_wellness": "DaySpa",
    "retail": "Store",
    "supermarket": "GroceryStore",
    "fashion": "ClothingStore",
    "electronics": "ElectronicsStore",
    "auto": "AutoRepair",
    "health_clinic": "MedicalClinic",
    "pharmacy": "Pharmacy",
    "education": "EducationalOrganization",
    "events_venue": "EventVenue",
    "transport": "LocalBusiness",
    "real_estate": "RealEstateAgent",
    "services": "ProfessionalService",
    "other": "LocalBusiness",
}

ORG_SAME_AS = [
    "https://www.instagram.com/afefehub",
    "https://github.com/victorlenerd/osaf",
]


def site() -> str:
    return get_settings().public_site_url.rstrip("/")


def org_node() -> dict:
    return {
        "@type": "Organization",
        "@id": f"{site()}/#org",
        "name": "Afefehub",
        "url": f"{site()}/",
        "logo": f"{site()}/icon-512.png",
        "description": (
            "Afefehub publishes authentic video and voice-note reviews of businesses across "
            "Africa, verified and summarised by AI."
        ),
        "parentOrganization": {
            "@type": "Organization",
            "name": "1CTECH",
            "url": "https://1ctech.ca",
        },
        "sameAs": ORG_SAME_AS,
    }


def website_node() -> dict:
    return {
        "@type": "WebSite",
        "@id": f"{site()}/#website",
        "name": "Afefehub",
        "url": f"{site()}/",
        "publisher": {"@id": f"{site()}/#org"},
    }


def breadcrumb_node(crumbs: list[tuple[str, str]]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": label, "item": f"{site()}{path}"}
            for i, (label, path) in enumerate(crumbs)
        ],
    }


def review_body(ext) -> str:
    parts = [ext.one_line_summary.strip()] if ext.one_line_summary else []
    if ext.good:
        parts.append("Good: " + "; ".join(ext.good) + ".")
    if ext.improve:
        parts.append("Could improve: " + "; ".join(ext.improve) + ".")
    return " ".join(p for p in parts if p)


def business_graph(page: BusinessPage) -> dict:
    b = page.business
    url = f"{site()}{page.path}"
    biz: dict = {
        "@type": SCHEMA_TYPES.get(b.category, "LocalBusiness"),
        "@id": f"{url}#business",
        "name": b.name,
        "url": url,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": b.formatted_address,
            **({"addressLocality": b.city} if b.city else {}),
            "addressCountry": b.country,
        },
    }
    if b.lat and b.lng:
        biz["geo"] = {"@type": "GeoCoordinates", "latitude": b.lat, "longitude": b.lng}
        biz["hasMap"] = f"https://www.google.com/maps/search/?api=1&query={b.lat},{b.lng}"
    if page.summary and page.summary.headline:
        biz["description"] = page.summary.headline
    if b.keywords:
        biz["keywords"] = ", ".join(
            k for k, _ in sorted(b.keywords.items(), key=lambda kv: -kv[1])[:10]
        )

    reviews = []
    for r in page.reviews:
        ext = r.extraction
        node: dict = {
            "@type": "Review",
            "@id": f"{url}#review-{r.review_id}",
            "author": {"@type": "Person", "name": reviewer_name(r)},
            "datePublished": r.created_at[:10],
            "reviewBody": review_body(ext),
            "publisher": {"@id": f"{site()}/#org"},
            "inLanguage": ext.language or "en",
        }
        if ext.rating:
            node["reviewRating"] = {
                "@type": "Rating",
                "ratingValue": ext.rating,
                "bestRating": 5,
                "worstRating": 1,
            }
        if r.source == "reel" and r.reel_shortcode:
            node["associatedMedia"] = {
                "@type": "VideoObject",
                "name": f"Video review of {b.name}",
                "description": ext.one_line_summary or f"Video review of {b.name}",
                "uploadDate": r.created_at[:10],
                "embedUrl": f"https://www.instagram.com/reel/{r.reel_shortcode}/embed",
                "url": r.reel_url or f"https://www.instagram.com/reel/{r.reel_shortcode}/",
            }
        reviews.append(node)
    if reviews:
        biz["review"] = reviews
    if page.show_aggregate and b.average_rating is not None:
        biz["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": b.average_rating,
            "ratingCount": b.rating_count,
            "reviewCount": b.review_count,
            "bestRating": 5,
            "worstRating": 1,
        }

    webpage = {
        "@type": "WebPage",
        "@id": url,
        "url": url,
        "name": f"{b.name} reviews",
        "isPartOf": {"@id": f"{site()}/#website"},
        "about": {"@id": f"{url}#business"},
        "dateModified": (page.summary.last_updated if page.summary else b.updated_at),
        "inLanguage": "en",
    }
    return {
        "@context": "https://schema.org",
        "@graph": [
            org_node(),
            website_node(),
            webpage,
            breadcrumb_node(page.breadcrumbs()),
            biz,
        ],
    }


def hub_graph(hub: Hub) -> dict:
    url = f"{site()}{hub.path}"
    graph: list[dict] = [org_node(), website_node(), breadcrumb_node(hub.breadcrumbs)]
    graph.append(
        {
            "@type": "CollectionPage",
            "@id": url,
            "url": url,
            "name": hub.title,
            "isPartOf": {"@id": f"{site()}/#website"},
            "inLanguage": "en",
            **({"dateModified": hub.updated_at} if hub.updated_at else {}),
        }
    )
    if hub.listings:
        graph.append(
            {
                "@type": "ItemList",
                "name": hub.title,
                "itemListOrder": "https://schema.org/ItemListOrderDescending",
                "numberOfItems": len(hub.top),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "url": f"{site()}{li.path}",
                        "name": li.business.name,
                    }
                    for i, li in enumerate(hub.top)
                ],
            }
        )
    return {"@context": "https://schema.org", "@graph": graph}


def to_script(data: dict) -> str:
    """JSON safe to embed in <script type="application/ld+json">."""
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


__all__ = ["business_graph", "country_name", "hub_graph", "to_script"]
