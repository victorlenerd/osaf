from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER = "CHANGEME"  # Terraform seeds SSM secrets with this; treat it as "not configured"


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

    # pipeline tuning
    max_clarification_rounds: int = 3
    face_coverage_threshold: float = 0.5
    dominant_speaker_threshold: float = 0.6
    stale_stage_seconds: int = 600
    phone_hash_salt: str = "afefehub"
    work_dir: str = "/tmp/afefehub"

    @field_validator("*", mode="before")
    @classmethod
    def _placeholder_is_unset(cls, v):
        return "" if isinstance(v, str) and v.strip() == PLACEHOLDER else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
