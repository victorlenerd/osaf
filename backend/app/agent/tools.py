"""Tool definitions (OpenAI function-calling schema) for the Muse Spark extraction agent."""

from __future__ import annotations

from app.models import CATEGORIES

REVIEW_FIELDS = [
    "business",
    "visit_time",
    "visit_location",
    "good",
    "improve",
    "recommend",
    "category",
]

SEARCH_PLACES = {
    "type": "function",
    "function": {
        "name": "search_places",
        "description": (
            "Search Google Places for the business being reviewed. Use the name as the reviewer "
            "says it plus any street, area or city mentioned; add the reviewer's known city if "
            "the review names none. Returns up to 5 candidates with place_id. Try a different "
            "query if results look wrong. Never invent a place_id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free text, e.g. 'Mama Put Allen Avenue Ikeja'",
                },
                "region_code": {
                    "type": "string",
                    "description": "ISO-3166 alpha-2 country code, e.g. NG, GH, KE",
                },
                "location_bias": {
                    "type": "object",
                    "description": "Optional city centre to bias results towards",
                    "properties": {
                        "lat": {"type": "number"},
                        "lng": {"type": "number"},
                        "radius_m": {"type": "integer"},
                    },
                },
            },
            "required": ["query", "region_code"],
        },
    },
}

ASK_USER = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Send the reviewer ONE short WhatsApp message asking for what you cannot determine. "
            "Bundle all unknowns into a single question. When offering place candidates, number "
            "them (1, 2, 3) so the reviewer can answer with a number. Calling this ends your "
            "turn; you will be re-invoked with the answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "maxLength": 700},
                "missing_fields": {
                    "type": "array",
                    "items": {"type": "string", "enum": REVIEW_FIELDS},
                },
                "candidates_shown": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "place_ids in the order you numbered them, if any",
                },
            },
            "required": ["question", "missing_fields"],
        },
    },
}

PLACE_REF_SCHEMA = {
    "type": "object",
    "properties": {
        "place_id": {
            "type": "string",
            "description": (
                "A place_id returned by search_places, or 'afefe:<name-slug>-<city-slug>' "
                "ONLY when Google has no entry after at least two different searches"
            ),
        },
        "name": {"type": "string"},
        "formatted_address": {"type": "string"},
        "lat": {"type": "number"},
        "lng": {"type": "number"},
        "country": {"type": "string", "description": "ISO-3166 alpha-2"},
        "city": {"type": "string"},
        "primary_type": {"type": "string"},
        "source": {"type": "string", "enum": ["google", "user"]},
    },
    "required": ["place_id", "name", "formatted_address", "country", "source"],
}

FINALIZE_REVIEW = {
    "type": "function",
    "function": {
        "name": "finalize_review",
        "description": (
            "Submit the completed extraction. Only call when the business is resolved "
            "(place_id from search_places, or an afefe: id after failed searches) and you have "
            "made a best effort on all other fields. Non-business fields may be empty/unknown."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "business": PLACE_REF_SCHEMA,
                "business_name_as_said": {
                    "type": "string",
                    "description": "The business name verbatim as the reviewer said it",
                },
                "visit": {
                    "type": "object",
                    "properties": {
                        "when_text": {
                            "type": "string",
                            "description": "e.g. 'last Saturday night'",
                        },
                        "when_iso": {
                            "type": "string",
                            "description": "YYYY-MM-DD if derivable, else omit",
                        },
                        "where_text": {
                            "type": "string",
                            "description": "Location in the reviewer's words",
                        },
                    },
                },
                "good": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-5 short points on what was good",
                },
                "improve": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "0-5 short points on what could improve",
                },
                "recommend": {"type": "string", "enum": ["yes", "no", "maybe"]},
                "category": {"type": "string", "enum": CATEGORIES},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-8 tags: dishes, products, services, vibe, e.g. jollof, suya",
                },
                "overall_sentiment": {"type": "string", "enum": ["positive", "mixed", "negative"]},
                "language": {
                    "type": "string",
                    "description": ("Main language: en, pcm (pidgin), yo, ha, ig, sw, fr, ar..."),
                },
                "confidence": {
                    "type": "object",
                    "description": (
                        "0-1 per field: business, visit, good, improve, recommend, category"
                    ),
                    "additionalProperties": {"type": "number"},
                },
                "one_line_summary": {"type": "string", "maxLength": 160},
            },
            "required": [
                "business",
                "business_name_as_said",
                "good",
                "improve",
                "recommend",
                "category",
                "keywords",
                "overall_sentiment",
                "language",
                "confidence",
                "one_line_summary",
            ],
        },
    },
}

REJECT_REVIEW = {
    "type": "function",
    "function": {
        "name": "reject_review",
        "description": (
            "Decline the submission because the video is not a business review (no business "
            "visited, no customer experience described). Calling this ends the submission; the "
            "reviewer is told to record a real review. Do not use it for a review that merely "
            "lacks a detail such as the branch or city: ask_user handles those."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "maxLength": 200,
                    "description": "One short line, shown to the reviewer, e.g. "
                    "'it is a vlog about driving, no business is mentioned'",
                }
            },
            "required": ["reason"],
        },
    },
}

ALL_TOOLS = [SEARCH_PLACES, ASK_USER, FINALIZE_REVIEW, REJECT_REVIEW]
TOOLS_NO_ASK = [SEARCH_PLACES, FINALIZE_REVIEW, REJECT_REVIEW]
