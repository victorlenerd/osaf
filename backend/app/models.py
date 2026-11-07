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
    "shortlet",
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

    # Instagram metadata from the download (reels only); the username is what the original-
    # author check compares against.
    ig_username: str | None = None
    ig_uploader_id: str | None = None
    ig_posted_at: str | None = None
    # Duplicate detection (app/fingerprint): exact hash of the media file, the stored
    # fingerprint, and the closest existing review when it is too similar to earn points.
    media_sha256: str | None = None
    s3_fingerprint_key: str | None = None
    similarity: SimilarityMatch | None = None
    similarity_checked: bool = False


class Conversation(BaseModel):
    phone: str
    active_submission_id: str | None = None
    profile_country: str | None = None
    profile_city: str | None = None
    display_name: str | None = None
    # Set when the reviewer texts "delete my data"; the erasure runs once they reply DELETE
    # within the confirmation window (app/pipeline/erase.py).
    deletion_requested_at: str | None = None
    # Set the moment the reviewer confirms; while it is recent, inbound messages are held off
    # so nothing is written back under an erasure that is still running.
    erasure_started_at: str | None = None
    # Businesses whose counters, summary and search document must be rebuilt once this
    # number's reviews are gone. Written before the first review is deleted so a retry after
    # a failed run still knows which businesses it touched.
    erasure_businesses: list[str] = Field(default_factory=list)
    # Payouts: when we last asked for bank details (the next message with an account number
    # is read as the answer), and when a banned number was last told so (at most once a day).
    payout_details_requested_at: str | None = None
    ban_notice_at: str | None = None
    updated_at: str = Field(default_factory=now_iso)
    # DynamoDB TTL: conversations are kept 12 months after the last message (privacy policy).
    expires_at: int | None = None


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
    # ISO-3166 alpha-2 of the WhatsApp number's dialing code (shown as a flag); coarse enough
    # to publish, unlike the number itself. None when the number did not parse.
    reviewer_country: str | None = None
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
    ig_username: str | None = None
    ig_uploader_id: str | None = None
    ig_posted_at: str | None = None
    # True once the sender has proven they posted the reel (app/rewards/verify.py); until then
    # the reel is credited to its Instagram handle, not to the sender (app/credit.py).
    ig_author_verified: bool = False
    media_sha256: str | None = None
    fingerprint_s3_key: str | None = None
    # Set when the review is too close to an existing one to earn points (it still publishes).
    similarity: SimilarityMatch | None = None
    similarity_checked: bool = False


# --------------------------------------------------------------------- fingerprints
class Fingerprint(BaseModel):
    """What app/fingerprint compares: stored as JSON in S3 and in the fingerprints index."""

    sha256: str | None = None
    audio: list[int] = Field(default_factory=list)  # Chromaprint raw sub-fingerprints (uint32)
    video: list[int] = Field(default_factory=list)  # 64-bit dHash per sampled frame
    text: list[int] = Field(default_factory=list)  # MinHash signature of the transcript


class SimilarityMatch(BaseModel):
    review_id: str
    business_id: str | None = None
    exact: bool = False
    audio: float = 0.0
    video: float = 0.0
    text: float = 0.0


# ------------------------------------------------------------------------- payouts
# reel_unverified: a reel entered before its author check; worth 0 until verified, and voided
# at settlement if it never is.
EntryKind = Literal["voice", "reel_unverified", "reel_author"]
EntryStatus = Literal["entered", "approved", "voided", "paid"]


class PayoutEntry(BaseModel):
    """One published review entered for a monthly payout window (RWD#<hash> / ENTRY#<rid>)."""

    review_id: str
    phone: str | None = None  # stripped when the reviewer erases their data after payment
    phone_hash: str
    business_id: str
    business_name: str = ""
    category: str = "other"
    group: str = "others"
    kind: EntryKind
    points: int
    window: str  # yyyy-mm, Africa/Lagos
    status: EntryStatus = "entered"
    ig_username: str | None = None
    ig_code: str | None = None  # open author-verification code, if any
    ig_verified_at: str | None = None
    similarity: SimilarityMatch | None = None
    similarity_checked: bool = True
    rate_ngn: float | None = None  # naira per point, set at settlement
    amount_ngn: int | None = None
    note: str | None = None
    entered_at: str = Field(default_factory=now_iso)
    decided_at: str | None = None
    paid_at: str | None = None


class PayoutOffer(BaseModel):
    """A published review the reviewer may still ENTER (RWD#<hash> / OFFER#<rid>, 7-day TTL)."""

    review_id: str
    phone: str
    created_at: str = Field(default_factory=now_iso)
    expires_at: int | None = None


class Payee(BaseModel):
    """How a reviewer wants to be paid (RWD#<hash> / PAYEE)."""

    phone: str
    method: Literal["bank", "amazon"] = "bank"
    bank_name: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    updated_at: str = Field(default_factory=now_iso)

    @property
    def complete(self) -> bool:
        if self.method == "amazon":
            return True
        return bool(self.bank_name and self.account_number and self.account_name)

    def masked(self) -> str:
        if self.method == "amazon":
            return "Amazon gift card"
        tail = (self.account_number or "")[-4:]
        return f"{self.bank_name} ****{tail} ({self.account_name})"


class Ban(BaseModel):
    """BAN#<phone_hash>. Kept after erasure (a keyed hash only) so a banned person cannot
    erase and come straight back."""

    phone_hash: str
    reason: str
    note: str = ""
    hide_reviews: bool = False
    reviews_hidden: int = 0
    entries_voided: int = 0
    ig_usernames: list[str] = Field(default_factory=list)
    banned_by: str = "operator"
    banned_at: str = Field(default_factory=now_iso)


# Submission and Review refer to SimilarityMatch, which is defined after them.
Submission.model_rebuild()
Review.model_rebuild()
