"""ISO-3166 alpha-2 country codes. Everything Afefehub stores, filters on or puts in a URL uses
the two-letter code (NG), never the name ("Nigeria") a model or Google's long text may give."""

from __future__ import annotations

import re

# Countries reviewers are most likely to name, plus common alternative spellings. Anything
# not here that is already two letters passes through.
_NAMES: dict[str, str] = {
    "algeria": "DZ",
    "angola": "AO",
    "benin": "BJ",
    "botswana": "BW",
    "burkina faso": "BF",
    "burundi": "BI",
    "cameroon": "CM",
    "cape verde": "CV",
    "cabo verde": "CV",
    "central african republic": "CF",
    "chad": "TD",
    "comoros": "KM",
    "congo": "CG",
    "republic of the congo": "CG",
    "democratic republic of the congo": "CD",
    "dr congo": "CD",
    "drc": "CD",
    "cote d'ivoire": "CI",
    "côte d'ivoire": "CI",
    "ivory coast": "CI",
    "djibouti": "DJ",
    "egypt": "EG",
    "equatorial guinea": "GQ",
    "eritrea": "ER",
    "eswatini": "SZ",
    "swaziland": "SZ",
    "ethiopia": "ET",
    "gabon": "GA",
    "gambia": "GM",
    "the gambia": "GM",
    "ghana": "GH",
    "guinea": "GN",
    "guinea-bissau": "GW",
    "kenya": "KE",
    "lesotho": "LS",
    "liberia": "LR",
    "libya": "LY",
    "madagascar": "MG",
    "malawi": "MW",
    "mali": "ML",
    "mauritania": "MR",
    "mauritius": "MU",
    "morocco": "MA",
    "mozambique": "MZ",
    "namibia": "NA",
    "niger": "NE",
    "nigeria": "NG",
    "rwanda": "RW",
    "sao tome and principe": "ST",
    "senegal": "SN",
    "seychelles": "SC",
    "sierra leone": "SL",
    "somalia": "SO",
    "south africa": "ZA",
    "south sudan": "SS",
    "sudan": "SD",
    "tanzania": "TZ",
    "togo": "TG",
    "tunisia": "TN",
    "uganda": "UG",
    "zambia": "ZM",
    "zimbabwe": "ZW",
    "canada": "CA",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "united arab emirates": "AE",
    "uae": "AE",
}
_ALPHA2 = re.compile(r"^[A-Za-z]{2}$")
# Two-letter values in common use that are not the ISO code. Checked before a two-letter value
# is passed through, so "UK" is stored as GB like every other spelling of the country.
_TWO_LETTER_ALIASES = {"UK": "GB"}


def country_code(value: str | None) -> str | None:
    """ "NG", "ng", "Nigeria", "NIGERIA" -> "NG". None for empty or unrecognised names, so a
    caller never stores a guess such as "NI"."""
    v = (value or "").strip().strip(".")
    if not v:
        return None
    if _ALPHA2.match(v):
        return _TWO_LETTER_ALIASES.get(v.upper(), v.upper())
    return _NAMES.get(" ".join(v.lower().split()))
