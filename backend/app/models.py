"""Pydantic models shared by the pipeline, the agent, the stores and the public API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class SubmissionState(StrEnum):
    NEW = "NEW"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    VERIFYING = "VERIFYING"
    EXTRACTING = "EXTRACTING"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    AWAITING_VIDEO = "AWAITING_VIDEO"  # download failed; user asked to send the file on WhatsApp
    PAUSED = "PAUSED"  # media saved, but the model API is not configured; resumable
    CONFIRMING = "CONFIRMING"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    ABANDONED = "ABANDONED"


TRANSIENT_STATES = {
    SubmissionState.NEW,
    SubmissionState.DOWNLOADING,
    SubmissionState.TRANSCRIBING,
    SubmissionState.VERIFYING,
    SubmissionState.EXTRACTING,
}
WAITING_STATES = {
    SubmissionState.AWAITING_CLARIFICATION,
    SubmissionState.AWAITING_VIDEO,
    SubmissionState.PAUSED,
    SubmissionState.CONFIRMING,
}
TERMINAL_STATES = {SubmissionState.PUBLISHED, SubmissionState.REJECTED, SubmissionState.ABANDONED}


Category = Literal[
    "restaurant",
    "street_food",
    "cafe",
    "bar_lounge",
    "hotel",
    "salon_barber",
    "spa_wellness",
    "retail",
    "supermarket",
    "fashion",
    "electronics",
    "auto",
    "health_clinic",
    "pharmacy",
    "education",
    "events_venue",
    "transport",
    "real_estate",
    "services",
    "other",
]
CATEGORIES: list[str] = list(Category.__args__)  # type: ignore[attr-defined]

Recommend = Literal["yes", "no", "maybe"]
Sentiment = Literal["positive", "mixed", "negative"]


class PlaceRef(BaseModel):
    place_id: str = Field(
        description="Google place id, or 'afefe:<slug>' for a user-sourced business"
    )
    name: str
    formatted_address: str
    lat: float | None = None
    lng: float | None = None
    country: str = Field(description="ISO-3166 alpha-2, e.g. NG")
    city: str | None = None
    primary_type: str | None = None
    source: Literal["google", "user"] = "google"


class Visit(BaseModel):
    when_text: str | None = None
    when_iso: str | None = None
    where_text: str | None = None


class ReviewExtraction(BaseModel):
    business: PlaceRef
    business_name_as_said: str
    visit: Visit = Field(default_factory=Visit)
    good: list[str] = Field(default_factory=list, max_length=6)
    improve: list[str] = Field(default_factory=list, max_length=6)
    recommend: Recommend = "maybe"
    category: Category = "other"
    keywords: list[str] = Field(default_factory=list, max_length=10)
    overall_sentiment: Sentiment = "mixed"
    language: str = "en"
    confidence: dict[str, float] = Field(default_factory=dict)
    one_line_summary: str = ""


class TranscriptTurn(BaseModel):
    turn_id: int | None = None
    speaker: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    text: str


class Transcript(BaseModel):
    text: str
    turns: list[TranscriptTurn] = Field(default_factory=list)
    audio_duration_ms: int | None = None
    language_hint: str | None = None

    @classmethod
    def from_asr(cls, raw: dict) -> Transcript:
        """Build from the /v1/asr/transcribe JSON response."""
        turns = [
            TranscriptTurn(
                turn_id=t.get("turnId"),
                speaker=t.get("speaker"),
                start_ms=t.get("startMs"),
                end_ms=t.get("endMs"),
                text=t.get("transcript") or "",
            )
            for t in raw.get("turns") or []
        ]
        return cls(
            text=raw.get("transcript") or " ".join(t.text for t in turns),
            turns=turns,
            audio_duration_ms=raw.get("audioDurationMs"),
        )

    def dominant_speaker_share(self) -> float:
        """Share of spoken time attributed to the most active speaker (1.0 when undiarized)."""
        totals: dict[str, int] = {}
        for t in self.turns:
            if t.start_ms is None or t.end_ms is None:
                continue
            totals[t.speaker or "A"] = totals.get(t.speaker or "A", 0) + max(
                0, t.end_ms - t.start_ms
            )
        if not totals:
            return 1.0
        return max(totals.values()) / max(1, sum(totals.values()))

    def as_prompt_text(self) -> str:
        if not self.turns:
            return self.text
        return "\n".join(f"[{t.speaker or '?'}] {t.text}" for t in self.turns if t.text.strip())


class FaceCheck(BaseModel):
    passed: bool
    face_frame_coverage: float = 0.0
    frames_total: int = 0
    frames_with_face: int = 0
    max_concurrent_faces: int = 0
    dominant_speaker_share: float = 1.0
    reason: str = ""


class QA(BaseModel):
    q: str
    a: str


class PlaceCandidate(BaseModel):
    place_id: str
    name: str
    formatted_address: str
    lat: float | None = None
    lng: float | None = None
    country: str | None = None
    city: str | None = None
    primary_type: str | None = None
    business_status: str | None = None  # OPERATIONAL | CLOSED_TEMPORARILY | CLOSED_PERMANENTLY


SubmissionKind = Literal["reel", "voice"]


class Submission(BaseModel):
    submission_id: str
    phone: str
    kind: SubmissionKind = "reel"
    reel_url: str | None = None  # reel submissions only
    reel_shortcode: str | None = None
    wa_media_id: str | None = None  # voice submissions: the WhatsApp media id of the note
    state: SubmissionState = SubmissionState.NEW
    state_updated_at: str = Field(default_factory=now_iso)
    error: str | None = None
    progress_note: str | None = None

    s3_video_key: str | None = None
    s3_audio_key: str | None = None
    s3_voice_key: str | None = None  # playable m4a of a voice-note review
    s3_transcript_key: str | None = None
    s3_facecheck_key: str | None = None
    transcript: Transcript | None = None
    face_check: FaceCheck | None = None

    collected: dict = Field(default_factory=dict)
    clarification_rounds: int = 0
    pending_question: str | None = None
    qa_log: list[QA] = Field(default_factory=list)
    place_candidates: list[PlaceCandidate] = Field(default_factory=list)
    extraction: ReviewExtraction | None = None

    review_id: str | None = None
    business_id: str | None = None
    created_at: str = Field(default_factory=now_iso)
    expires_at: int | None = None


class Conversation(BaseModel):
    phone: str
    active_submission_id: str | None = None
    profile_country: str | None = None
    profile_city: str | None = None
    display_name: str | None = None
    updated_at: str = Field(default_factory=now_iso)


class BusinessSummary(BaseModel):
    overall_sentiment: Sentiment = "mixed"
    headline: str = ""
    recurring_praise: list[str] = Field(default_factory=list)
    recurring_complaints: list[str] = Field(default_factory=list)
    standout_items: list[str] = Field(default_factory=list)
    recommendation_rate: float = 0.0
    review_count: int = 0
    last_review_at: str | None = None
    last_updated: str = Field(default_factory=now_iso)
    model_version: str = "muse-spark-1.3"


# ------------------------------------------------------------ Google reviews (on demand)
class GoogleReview(BaseModel):
    """One Google review as returned by Place Details. Never persisted (Google ToS)."""

    author_name: str = ""
    author_uri: str | None = None
    author_photo_uri: str | None = None
    rating: int | None = None
    text: str = ""  # verbatim; empty for rating-only reviews
    language: str | None = None
    relative_time: str = ""
    publish_time: str | None = None
    google_maps_uri: str | None = None


class GooglePlaceDetails(BaseModel):
    place_id: str
    name: str
    formatted_address: str = ""
    city: str | None = None
    country: str | None = None
    lat: float | None = None
    lng: float | None = None
    primary_type: str | None = None
    rating: float | None = None
    user_rating_count: int = 0
    google_maps_uri: str | None = None
    business_status: str | None = None
    reviews: list[GoogleReview] = Field(default_factory=list)


class GoogleReviewSummary(BaseModel):
    """AI summary of a place's Google reviews; cached in Dynamo under GPLACE#<id> with a TTL."""

    overall_sentiment: Sentiment = "mixed"
    headline: str = ""
    recurring_praise: list[str] = Field(default_factory=list)
    recurring_complaints: list[str] = Field(default_factory=list)
    standout_items: list[str] = Field(default_factory=list)
    rating: float | None = None
    user_rating_count: int = 0
    reviews_considered: int = 0
    generated_at: str = Field(default_factory=now_iso)
    model_version: str = "muse-spark-1.3"
    expires_at: int | None = None  # Dynamo TTL attribute; set before put


class Business(BaseModel):
    business_id: str
    source: Literal["google", "user"] = "google"
    name: str
    formatted_address: str
    country: str
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    category: str = "other"
    google_primary_type: str | None = None
    review_count: int = 0
    recommend_counts: dict[str, int] = Field(
        default_factory=lambda: {"yes": 0, "no": 0, "maybe": 0}
    )
    keywords: dict[str, int] = Field(default_factory=dict)
    names_as_said: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @property
    def recommend_rate(self) -> float:
        total = sum(self.recommend_counts.values())
        return (self.recommend_counts.get("yes", 0) / total) if total else 0.0


class Review(BaseModel):
    review_id: str
    business_id: str
    submission_id: str
    reviewer_phone_hash: str
    reviewer_display_name: str | None = None
    source: SubmissionKind = "reel"
    reel_url: str | None = None
    reel_shortcode: str | None = None
    extraction: ReviewExtraction
    transcript_s3_key: str | None = None
    video_s3_key: str | None = None
    audio_s3_key: str | None = None  # voice reviews: playable m4a
    face_check: FaceCheck | None = None
    created_at: str = Field(default_factory=now_iso)
    status: Literal["published", "hidden"] = "published"
