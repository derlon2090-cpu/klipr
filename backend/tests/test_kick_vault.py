from datetime import datetime, timezone

from app.core.crypto import decrypt_secret, encrypt_secret
from app.api.credentials import extract_cookie_expiry, public_credential
from app.models import SessionCredential


def test_fernet_round_trip_never_returns_ciphertext_as_secret():
    secret = "kick_session=not-for-logs"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_netscape_cookie_expiry_uses_earliest_non_session_timestamp():
    content = "# Netscape HTTP Cookie File\n.kick.com\tTRUE\t/\tTRUE\t1900000000\ta\tone\n.kick.com\tTRUE\t/\tTRUE\t1800000000\tb\ttwo\n"
    assert extract_cookie_expiry(content) == datetime.fromtimestamp(1800000000, tz=timezone.utc)


def test_token_has_no_netscape_expiry():
    assert extract_cookie_expiry("Bearer a-session-token") is None


def test_public_credential_response_never_leaks_encrypted_or_raw_secret():
    raw = "kick_session=private"
    result = public_credential(SessionCredential(platform="kick", session_encrypted=encrypt_secret(raw), status="active"), "kick")
    assert set(result) == {"platform", "has_session", "status", "updated_at", "expires_at"}
    assert raw not in str(result)
