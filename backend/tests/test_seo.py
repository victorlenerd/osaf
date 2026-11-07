"""Crawlable pages: slugs, the rendered HTML and Markdown, JSON-LD, hubs, the site publisher
and the erasure hooks that keep the pages in step with the data."""

from __future__ import annotations

import json
import re

import pytest

from app.models import Business, BusinessSummary, PlaceRef, Review, ReviewExtraction
from app.seo import model, render, site
from app.seo.model import BusinessPage, Listing, build_hubs, score
from app.seo.slugs import business_slug, hub_path, slugify


# ------------------------------------------------------------------------ helpers
def biz(bid="ChIJ1", name="Mama Cass", city="Lagos", category="restaurant", **kw) -> Business:
    defaults = dict(
        review_count=2,
        recommend_counts={"yes": 2, "no": 0, "maybe": 0},
        updated_at="2026-11-01T10:00:00Z",
        lat=6.45,
        lng=3.4,
    )
    defaults.update(kw)
    return Business(
        business_id=bid,
        name=name,
        city=city,
        formatted_address=f"1 Admiralty Way, {city}",
        country="NG",
        category=category,
        **defaults,
    )


def review(rid="r1", bid="ChIJ1", rating=None, source="reel", **ext) -> Review:
    e = dict(
        business=PlaceRef(place_id=bid, name="Mama Cass", formatted_address="a", country="NG"),
        business_name_as_said="mama cass",
        good=["jollof", "fast service"],
        improve=["parking"],
        recommend="yes",
        one_line_summary="Great jollof, slow parking.",
        rating=rating,
    )
    e.update(ext)
    return Review(
        review_id=rid,
        business_id=bid,
        submission_id=f"s-{rid}",
        reviewer_phone_hash="h",
        reviewer_display_name="Ada",
        reviewer_country="NG",
        source=source,
        reel_shortcode="ABC123" if source == "reel" else None,
        reel_url="https://www.instagram.com/reel/ABC123/" if source == "reel" else None,
        created_at=f"2026-10-2{rid[-1]}T09:00:00Z",
        extraction=ReviewExtraction(**e),
    )


SUMMARY = BusinessSummary(
    overall_sentiment="positive",
    headline="Loved for its jollof and quick service",
    recurring_praise=["jollof rice", "quick service"],
    recurring_complaints=["parking"],
    standout_items=["smoky jollof"],
    review_count=2,
    last_updated="2026-11-01T10:00:00Z",
)


def jsonld(html: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert m, "no JSON-LD"
    return json.loads(m.group(1))


def node(graph: dict, type_: str) -> dict:
    return next(n for n in graph["@graph"] if n["@type"] == type_)


# ------------------------------------------------------------------------- slugs
def test_slugify_folds_accents_and_punctuation():
    assert slugify("Café Néo — Lekki Phase 1!") == "cafe-neo-lekki-phase-1"
    assert slugify("") == ""
    assert len(slugify("x" * 200)) <= 48


def test_business_slug_is_stable_unique_and_readable():
    a = business_slug("ChIJ1", "Mama Cass", "Lagos")
    assert a.startswith("mama-cass-lagos-") and a == business_slug("ChIJ1", "Mama Cass", "Lagos")
    assert a != business_slug("ChIJ2", "Mama Cass", "Lagos")  # same name, same city
    # city not repeated when the name already ends with it
    assert business_slug("x", "Radisson Lagos", "Lagos").startswith("radisson-lagos-")
    assert not business_slug("x", "Radisson Lagos", "Lagos").startswith("radisson-lagos-lagos")
    assert biz().slug == a


def test_hub_paths():
    assert hub_path("NG") == "/places/ng"
    assert hub_path("NG", "lagos") == "/places/ng/lagos"
    assert hub_path("NG", "lagos", "bar_lounge") == "/places/ng/lagos/bars-and-lounges"


# ------------------------------------------------------------------- business page
def page(**kw) -> BusinessPage:
    b = kw.pop("business", None) or biz()
    reviews = kw.pop("reviews", None) or [review("r2"), review("r1", source="voice")]
    return BusinessPage(business=b, summary=kw.pop("summary", SUMMARY), reviews=reviews)


def test_business_page_has_crawlable_content_and_meta():
    p = page()
    out = render.render_business(p)
    html = out.html
    assert f'<link rel="canonical" href="https://afefehub.com/b/{p.business.slug}">' in html
    assert "<h1>Mama Cass</h1>" in html
    assert "Mama Cass, Lagos: reviews &amp; what people say | Afefehub</title>" in html
    assert 'content="index,follow' in html
    # the answer-first paragraph carries the facts an assistant would quote
    assert "Mama Cass in Lagos has 2 video and voice-note reviews on Afefehub." in html
    assert "100% of reviewers recommend it." in html
    assert "Reviewers praise: jollof rice; quick service." in html
    # every review, newest first, with the reel embed and the voice audio redirect
    assert html.index("review-r2") < html.index("review-r1")
    assert "instagram.com/reel/ABC123/" in html and "instagram.com/embed.js" in html
    assert "/api/review/r1/audio" not in html  # voice review without audio key: no player
    assert f'href="https://afefehub.com/b/{p.business.slug}.md"' in html
    # breadcrumbs link to the hubs
    assert 'href="/places/ng/lagos/restaurants"' in html


def test_business_markdown_twin():
    md = render.render_business(page()).md
    assert md.startswith("# Mama Cass — reviews on Afefehub")
    assert "- Canonical page: https://afefehub.com/b/" in md
    assert "### Ada, 22 Oct 2026 (video review)" in md
    assert "- Good: jollof; fast service" in md


def test_user_text_is_escaped_in_html_and_jsonld():
    b = biz(name="</script><script>alert(1)</script>")
    html = render.render_business(page(business=b)).html
    assert "<script>alert(1)" not in html
    assert jsonld(html)  # still parses


def test_jsonld_local_business_reviews_and_no_aggregate_below_threshold():
    b = biz(rating_sum=9, rating_count=2)
    reviews = [review("r2", rating=5), review("r1", rating=4)]
    g = jsonld(render.render_business(page(business=b, reviews=reviews)).html)
    lb = node(g, "Restaurant")
    assert lb["name"] == "Mama Cass" and lb["address"]["addressCountry"] == "NG"
    assert lb["geo"]["latitude"] == 6.45
    assert [r["reviewRating"]["ratingValue"] for r in lb["review"]] == [5, 4]
    assert lb["review"][0]["associatedMedia"]["@type"] == "VideoObject"
    assert "aggregateRating" not in lb
    assert node(g, "BreadcrumbList")["itemListElement"][-1]["name"] == "Mama Cass"


def test_jsonld_aggregate_rating_from_three_rated_reviews():
    b = biz(review_count=4, rating_sum=13, rating_count=3)
    reviews = [review("r4", rating=5), review("r3", rating=4), review("r2", rating=4), review("r1")]
    g = jsonld(render.render_business(page(business=b, reviews=reviews)).html)
    agg = node(g, "Restaurant")["aggregateRating"]
    assert agg == {
        "@type": "AggregateRating",
        "ratingValue": 4.33,
        "ratingCount": 3,
        "reviewCount": 4,
        "bestRating": 5,
        "worstRating": 1,
    }
    # an unrated review carries no reviewRating
    assert "reviewRating" not in node(g, "Restaurant")["review"][3]


def test_google_place_page_never_embeds_google_reviews():
    """Places ToS: Google reviews are only fetched in the browser, never rendered or indexed."""
    html = render.render_business(page()).html
    assert 'id="google-reviews"' in html and "data-nosnippet" in html
    section = re.search(r'<section id="google-reviews".*?</section>', html, re.S).group(0)
    assert "Google" not in re.sub(r"<[^>]+>", "", section)
    assert "/seo.js" in html


def test_category_maps_to_schema_type():
    g = jsonld(render.render_business(page(business=biz(category="salon_barber"))).html)
    assert node(g, "HairSalon")


# ---------------------------------------------------------------------------- hubs
def listing(bid, name, city="Lagos", category="restaurant", yes=1, no=0, **kw):
    b = biz(
        bid=bid,
        name=name,
        city=city,
        category=category,
        review_count=yes + no,
        recommend_counts={"yes": yes, "no": no, "maybe": 0},
        **kw,
    )
    return Listing(business=b, summary=None)


def test_score_prefers_many_good_reviews_over_one():
    one = biz(review_count=1, recommend_counts={"yes": 1, "no": 0, "maybe": 0})
    many = biz(review_count=20, recommend_counts={"yes": 18, "no": 2, "maybe": 0})
    assert score(many) > score(one)
    loved = biz(review_count=3, recommend_counts={"yes": 3}, rating_sum=15, rating_count=3)
    meh = biz(review_count=3, recommend_counts={"yes": 3}, rating_sum=6, rating_count=3)
    assert score(loved) > score(meh)


def test_build_hubs_groups_ranks_and_gates_indexing():
    ls = [
        listing("a", "A", yes=5),
        listing("b", "B", yes=1, no=3),
        listing("c", "C", yes=3),
        listing("d", "D", city="Abuja", category="hotel", yes=2),
    ]
    hubs = build_hubs(ls)
    assert set(hubs) == {
        "/places",
        "/places/ng",
        "/places/ng/lagos",
        "/places/ng/lagos/restaurants",
        "/places/ng/abuja",
        "/places/ng/abuja/hotels",
    }
    lagos = hubs["/places/ng/lagos/restaurants"]
    assert [li.business.name for li in lagos.listings] == ["A", "C", "B"]
    assert lagos.indexable and not hubs["/places/ng/abuja/hotels"].indexable
    assert lagos.title == "Best-reviewed restaurants in Lagos, Nigeria"
    out = render.render_hub(lagos)
    assert "the best-reviewed restaurants in Lagos, Nigeria on Afefehub are A, C and B" in out.html
    assert node(jsonld(out.html), "ItemList")["itemListElement"][0]["name"] == "A"
    abuja = render.render_hub(hubs["/places/ng/abuja/hotels"]).html
    assert 'content="noindex,follow"' in abuja
    assert "](https://afefehub.com/b/" in out.md


def test_sitemaps_list_reviewed_pages_and_indexable_hubs_only():
    ls = [listing("a", "A"), listing("b", "B"), listing("c", "C"), listing("d", "D", city="Abuja")]
    hubs = build_hubs(ls)
    maps = render.render_sitemaps(ls, hubs)
    assert set(maps) == {
        "sitemap.xml",
        "sitemaps/businesses.xml",
        "sitemaps/hubs.xml",
        "sitemaps/static.xml",
    }
    assert maps["sitemaps/businesses.xml"].count("<url>") == 4
    assert "/places/ng/lagos</loc>" in maps["sitemaps/hubs.xml"]
    assert "/places/ng/abuja</loc>" not in maps["sitemaps/hubs.xml"]  # 1 business: noindex
    assert "https://afefehub.com/sitemaps/businesses.xml" in maps["sitemap.xml"]


def test_llms_txt_lists_places_businesses_and_agent_endpoints():
    ls = [listing("a", "A"), listing("b", "B"), listing("c", "C")]
    txt = render.render_llms(ls, build_hubs(ls), "2026-11-07")
    assert txt.startswith("# Afefehub\n\n> ")
    assert "[Nigeria](https://afefehub.com/places/ng.md)" in txt
    assert "[Lagos](https://afefehub.com/places/ng/lagos.md)" in txt
    assert "https://api.afefehub.com/mcp" in txt
    assert "openapi-public.json" in txt


def test_llms_full_is_capped():
    full = render.render_llms_full(["# a\n" + "x" * 600, "# b\n" + "y" * 600], max_bytes=800)
    assert "# a" in full and "# b" not in full and "Truncated" in full


# ------------------------------------------------------------------ site publisher
class FakeStore:
    """The slice of app.store.dynamo the site publisher reads."""

    def __init__(self):
        self.businesses: dict[str, Business] = {}
        self.reviews: dict[str, list[Review]] = {}

    def get_business(self, bid):
        return self.businesses.get(bid)

    def list_reviews(self, bid, limit=100):
        return list(self.reviews.get(bid, []))

    def get_summary(self, bid):
        return SUMMARY if bid in self.businesses else None

    def list_all_businesses(self):
        return list(self.businesses.values())


@pytest.fixture
def world(monkeypatch, tmp_path):
    store = FakeStore()
    for bid, name in [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]:
        store.businesses[bid] = biz(bid=bid, name=name)
        store.reviews[bid] = [review("r1", bid=bid)]
    monkeypatch.setattr(site, "dynamo", store)
    return store, site.DirSiteWriter(tmp_path)


def test_publish_writes_page_hubs_and_shared_indexes(world):
    store, w = world
    assert site.publish_business_page("a", writer=w)
    slug = store.businesses["a"].slug
    files = set(w.list(""))
    assert {f"b/{slug}.html", f"b/{slug}.md"} <= files
    assert {
        "places.html",
        "places/ng.html",
        "places/ng/lagos.html",
        "places/ng/lagos/restaurants.md",
        "sitemap.xml",
        "sitemaps/businesses.xml",
        "llms.txt",
    } <= files
    assert w.invalidated == [f"/b/{slug}", f"/b/{slug}.md"]
    # related businesses link to each other
    html = (w.root / f"b/{slug}.html").read_text()
    assert store.businesses["b"].slug in html


def test_publish_is_a_noop_without_a_site_bucket(world):
    site.default_writer.cache_clear()
    assert site.publish_business_page("a") is False


def test_removed_business_page_and_empty_hubs_are_pruned(world):
    store, w = world
    store.businesses["d"] = biz(bid="d", name="Delta", city="Abuja", category="hotel")
    store.reviews["d"] = [review("r1", bid="d")]
    site.render_all(writer=w)
    d_slug = store.businesses["d"].slug
    assert (w.root / f"b/{d_slug}.html").exists() and (w.root / "places/ng/abuja.html").exists()
    assert (w.root / "llms-full.txt").exists()

    del store.businesses["d"], store.reviews["d"]  # its last review was erased
    w.invalidated.clear()
    assert site.remove_business_page("d", writer=w)
    assert not (w.root / f"b/{d_slug}.html").exists()
    assert not (w.root / f"b/{d_slug}.md").exists()
    assert not (w.root / "places/ng/abuja.html").exists()
    assert not (w.root / "places/ng/abuja/hotels.html").exists()
    assert f"/b/{d_slug}" in w.invalidated
    assert d_slug not in (w.root / "sitemaps/businesses.xml").read_text()
    assert "Delta" not in (w.root / "llms.txt").read_text()
    # the other businesses are untouched
    assert (w.root / f"b/{store.businesses['a'].slug}.html").exists()


def test_rebuilt_business_page_drops_the_erased_review(world):
    store, w = world
    store.reviews["a"] = [review("r1", bid="a"), review("r2", bid="a", reviewer_display_name="x")]
    site.publish_business_page("a", writer=w)
    slug = store.businesses["a"].slug
    assert "review-r2" in (w.root / f"b/{slug}.html").read_text()
    store.reviews["a"] = [review("r1", bid="a")]
    site.publish_business_page("a", writer=w)
    assert "review-r2" not in (w.root / f"b/{slug}.html").read_text()


def test_hidden_reviews_are_not_rendered(world):
    store, w = world
    hidden = review("r2", bid="a")
    hidden.status = "hidden"
    store.reviews["a"].append(hidden)
    site.publish_business_page("a", writer=w)
    assert "review-r2" not in (w.root / f"b/{store.businesses['a'].slug}.html").read_text()


def test_key_path_round_trip():
    assert site.page_key("/b/x", "html") == "b/x.html"
    assert site.key_path("b/x.html") == "/b/x"
    assert site.page_key("/places", "md") == "places.md"


def test_model_constants_are_sane():
    assert model.MIN_INDEXABLE_HUB >= 2 and model.MIN_RATED_FOR_AGGREGATE >= 3


def test_demo_businesses_never_become_pages(world):
    """Fictional seed rows (afefe:demo-*) must not reach crawlable pages, sitemaps or llms.txt."""
    store, w = world
    store.businesses["afefe:demo-x"] = biz(bid="afefe:demo-x", name="Demo Spot")
    store.reviews["afefe:demo-x"] = [review("r1", bid="afefe:demo-x")]
    site.render_all(writer=w)
    assert not any("demo-spot" in k for k in w.list("b/"))
    assert "Demo Spot" not in (w.root / "llms.txt").read_text()
    assert "Demo Spot" not in (w.root / "places/ng/lagos.html").read_text()
    site.publish_business_page("afefe:demo-x", writer=w)
    assert not any("demo-spot" in k for k in w.list("b/"))
