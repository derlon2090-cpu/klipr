from unittest.mock import patch

from app.config import get_settings
from app.storage import r2_client


def test_storage_client_uses_path_style_for_s3_compatible_providers(monkeypatch):
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://storage.example.test")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_REGION", "us-east-2")
    get_settings.cache_clear()
    try:
        with patch("app.storage.boto3.client") as client:
            r2_client()
        kwargs = client.call_args.kwargs
        assert kwargs["config"].s3["addressing_style"] == "path"
        assert kwargs["config"].signature_version == "s3v4"
    finally:
        get_settings.cache_clear()
