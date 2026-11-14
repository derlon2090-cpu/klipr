from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str = "klipr-cloud"
    r2_region: str = "auto"
    recording_chunk_seconds: int = 300
    recording_max_reconnects: int = 8
    egress_proxy_url: str | None = None
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    audio_clean_timeout_seconds: int = 900
    r2_presigned_url_ttl_seconds: int = 3600
    klipr_access_password: str = ""
    klipr_session_secret: str = ""
    klipr_allowed_email: str = "klipr.cloud@gmail.com"
    klipr_secure_cookies: bool = False
    klipr_cors_origins: str = "https://klipr.cloud,https://klipr-zeta.vercel.app"
    klipr_studio_url: str = "https://klipr.cloud"
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_eventsub_secret: str = ""
    twitch_eventsub_callback_url: str = ""
    watcher_proxy_url: str | None = None
    ollama_url: str | None = None
    ollama_model: str = "qwen3:1.7b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
