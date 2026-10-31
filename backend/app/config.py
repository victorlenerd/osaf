from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER = "CHANGEME"  # Terraform seeds SSM secrets with this; treat it as "not configured"

# Settings a prod deployment cannot run without. Anything missing aborts startup rather than
# letting the service fail open (unsigned webhooks, guessable hashes, dry-run WhatsApp sends).
REQUIRED_IN_PROD = (
    "model_api_key",
    "meta_app_secret",
    "whatsapp_access_token",
    "whatsapp_phone_number_id",
    "whatsapp_verify_token",
    "phone_hash_salt",
)
MIN_SECRET_LEN = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    # Meta Model API — one key for Muse Spark, Muse Voice Transcribe and SAM 3.1
    model_api_key: str = ""
    meta_api_base: str = "https://api.meta.ai/v1"
    spark_model: str = "muse-spark-1.3"
    asr_model: str = "muse-voice-transcribe-1.0"
    sam_model: str = "sam-3.1"

    google_places_api_key: str = ""
    # On-demand Google reviews: how long the generated summary is cached (raw reviews never are),
    # and how long a browser-facing request may wait on Muse Spark for that summary.
    google_summary_ttl_seconds: int = 86400
    google_summary_timeout_seconds: int = 20

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "change-me"
    meta_app_secret: str = ""
    graph_api_version: str = "v21.0"

    ig_cookies_b64: str = ""

    aws_region: str = "us-east-1"
    dynamo_table: str = "afefehub"
    media_bucket: str = "afefehub-media-prod"
    opensearch_endpoint: str = ""  # host only, e.g. search-xxx.us-east-1.es.amazonaws.com
    opensearch_index: str = "businesses"
    public_site_url: str = "https://afefehub.com"
    public_api_url: str = "https://api.afefehub.com"  # absolute base for URLs the API hands out

    # pipeline tuning
    max_clarification_rounds: int = 3
    face_coverage_threshold: float = 0.5
    dominant_speaker_threshold: float = 0.6
    stale_stage_seconds: int = 600
    max_voice_note_seconds: int = 600  # Muse Voice Transcribe file limit is 10 minutes
    weekly_review_limit: int = 3  # published reviews per reviewer in any rolling 7 days
    points_per_review: int = 10  # flat reward per published review
    # Reels longer or larger than this are refused before download (disk and model cost cap).
    max_reel_seconds: int = 900
    max_reel_bytes: int = 500 * 1024 * 1024
    # Secret key for the reviewer phone hash (HMAC). Required in prod; see app/pii.py.
    phone_hash_salt: str = ""
    work_dir: str = "/tmp/afefehub"

    @field_validator("*", mode="before")
    @classmethod
    def _placeholder_is_unset(cls, v):
        return "" if isinstance(v, str) and v.strip() == PLACEHOLDER else v

    @model_validator(mode="after")
    def _prod_is_fully_configured(self):
        if self.env != "prod":
            return self
        problems = [name.upper() for name in REQUIRED_IN_PROD if not getattr(self, name)]
        for name in ("whatsapp_verify_token", "phone_hash_salt"):
            value = getattr(self, name)
            if value and (value == "change-me" or len(value) < MIN_SECRET_LEN):
                problems.append(f"{name.upper()} (too short or still the default)")
        if problems:
            raise ValueError(
                "ENV=prod but these settings are not configured: " + ", ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
