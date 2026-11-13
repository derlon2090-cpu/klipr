from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
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
    r2_presigned_url_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
