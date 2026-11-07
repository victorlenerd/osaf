"""Country values are always ISO-3166 alpha-2 codes, whatever form Google or the model use."""

from __future__ import annotations

import pytest

from app.agent.extract import _coerce
from app.countries import country_code
from app.models import PlaceCandidate


@pytest.mark.parametrize(
    "raw,code",
    [
        ("NG", "NG"),
        ("ng", "NG"),
        ("Nigeria", "NG"),
        ("NIGERIA", "NG"),
        (" south  africa ", "ZA"),
        ("Côte d'Ivoire", "CI"),
        ("Ivory Coast", "CI"),
        ("", None),
        (None, None),
        ("Atlantis", None),  # never a guess like "AT"
        ("UK", "GB"),  # a two-letter alias, not the ISO code
        ("uk", "GB"),
        ("United Kingdom", "GB"),
        ("GB", "GB"),
    ],
)
def test_country_code(raw, code):
    assert country_code(raw) == code


def test_google_candidate_with_a_country_name_is_stored_as_its_code():
    """The bug behind The Delborough: Google's long country name, upper-cased, was stored."""
    cand = PlaceCandidate(
        place_id="ChIJ1", name="The Delborough Lagos", formatted_address="a", country="Nigeria"
    )
    ext = _coerce(
        {
            "business": {"place_id": "ChIJ1", "name": "x", "formatted_address": "a"},
            "business_name_as_said": "delborough",
        },
        {"ChIJ1": cand},
    )
    assert ext.business.country == "NG"


def test_user_sourced_business_country_name_becomes_code():
    ext = _coerce(
        {
            "business": {"place_id": "", "name": "Mama Put", "formatted_address": "a",
                         "country": "Ghana", "city": "Accra"},
            "business_name_as_said": "mama put",
        },
        {},
    )  # fmt: skip
    assert ext.business.country == "GH"


def test_places_search_asks_for_the_short_country_code(monkeypatch):
    from app.agent import places

    body = {
        "places": [
            {
                "id": "ChIJ1",
                "displayName": {"text": "The Delborough Lagos"},
                "formattedAddress": "Victoria Island, Lagos",
                "addressComponents": [
                    {"longText": "Nigeria", "shortText": "NG", "types": ["country"]},
                ],
            }
        ]
    }

    class R:
        status_code = 200

        def json(self):
            return body

    monkeypatch.setattr(places.get_settings(), "google_places_api_key", "k")
    monkeypatch.setattr(places.httpx, "post", lambda *a, **k: R())
    out = places.search_places("delborough", "NG")
    assert out[0].country == "NG"


def test_fix_countries_script_repairs_reindexes_and_flags_unknowns(monkeypatch, capsys):
    import sys
    from pathlib import Path

    from app.models import Business

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import fix_countries

    rows = {
        "a": Business(business_id="a", name="Delborough", formatted_address="x", country="NIGERIA"),
        "b": Business(business_id="b", name="Ofe Otito", formatted_address="x", country="NG"),
        "c": Business(business_id="c", name="Odd", formatted_address="x", country="Atlantis"),
    }
    indexed: list[tuple[str, str]] = []

    class Store:
        def list_all_businesses(self):
            return list(rows.values())

        def set_business_country(self, bid, cc):
            rows[bid] = rows[bid].model_copy(update={"country": cc})

        def get_business(self, bid):
            return rows[bid]

        def get_summary(self, bid):
            return None

    monkeypatch.setattr(fix_countries, "dynamo", Store())
    monkeypatch.setattr(
        fix_countries.opensearch,
        "upsert_business",
        lambda b, s: indexed.append((b.business_id, b.country)),
    )
    monkeypatch.setattr(sys, "argv", ["fix_countries.py"])
    assert fix_countries.main() == 0 and rows["a"].country == "NIGERIA"  # dry run writes nothing

    monkeypatch.setattr(sys, "argv", ["fix_countries.py", "--apply"])
    assert fix_countries.main() == 1  # an unknown country is left for a person
    assert rows["a"].country == "NG" and rows["c"].country == "Atlantis"
    assert indexed == [("a", "NG")]
    assert "UNKNOWN country 'Atlantis'" in capsys.readouterr().err
