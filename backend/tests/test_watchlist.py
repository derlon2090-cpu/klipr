import pytest
import hashlib
import hmac
from datetime import datetime, timezone
from fastapi import HTTPException

from app.main import normalize_live_url
from app.worker.watcher import delayed_action
from app.config import get_settings
from app.twitch_eventsub import verify_eventsub_signature


@pytest.mark.parametrize("url", ["https://twitch.tv/creator", "https://kick.com/creator"])
def test_watchlist_accepts_exact_provider_urls(url):
    assert normalize_live_url(url)[1] == url


@pytest.mark.parametrize("url", ["http://twitch.tv/name", "https://kick.com.evil.test/name", "https://localhost/name"])
def test_watchlist_rejects_unsafe_urls(url):
    with pytest.raises(HTTPException):
        normalize_live_url(url)


def test_manual_recording_lock_prevents_duplicate():
    assert delayed_action("pending_auto_record", lock_exists=True) == "manual_taken_over"


def test_cancelled_notification_never_starts():
    assert delayed_action("cancelled", lock_exists=False) == "skip"


def test_uncancelled_notification_starts_without_lock():
    assert delayed_action("pending_auto_record", lock_exists=False) == "start"


def test_twitch_eventsub_hmac_verification(monkeypatch):
    secret, message_id, body = "0123456789abcdef", "message-1", b'{"event":{}}'
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    signature = "sha256=" + hmac.new(secret.encode(), message_id.encode() + timestamp.encode() + body, hashlib.sha256).hexdigest()
    monkeypatch.setenv("TWITCH_EVENTSUB_SECRET", secret); get_settings.cache_clear()
    try:
        assert verify_eventsub_signature(message_id, timestamp, body, signature)
        assert not verify_eventsub_signature(message_id, timestamp, body + b"x", signature)
    finally:
        get_settings.cache_clear()
