import pytest
from fastapi import HTTPException
from app.main import normalize_live_url, validate_creator_options

@pytest.mark.parametrize(("url", "platform"), [("https://kick.com/creator", "kick"), ("https://twitch.tv/creator", "twitch")])
def test_only_allowed_https_provider_urls_pass(url, platform): assert normalize_live_url(url)[0] == platform

@pytest.mark.parametrize("url", ["http://kick.com/creator", "https://localhost/creator", "https://127.0.0.1/x", "https://kick.com.evil.com/user", "https://twitch.tv@evil.com/user", "https://kick.com:444/user"])
def test_ssrf_and_lookalike_urls_are_rejected(url):
    with pytest.raises(HTTPException) as error: normalize_live_url(url)
    assert error.value.status_code == 422

@pytest.mark.parametrize("webhook", ["http://discord.com/api/webhooks/1/token", "https://discord.com.evil.com/api/webhooks/1/token", "https://discord.com/api/webhooks/not-id/token", "https://example.com/api/webhooks/1/token"])
def test_invalid_discord_webhooks_are_rejected(webhook):
    with pytest.raises(HTTPException): validate_creator_options("center", webhook)

def test_official_discord_webhook_and_layout_are_accepted(): assert validate_creator_options("split", "https://discord.com/api/webhooks/12345/token_ABC")[0] == "split"
