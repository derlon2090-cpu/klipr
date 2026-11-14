"""Minimal official Twitch EventSub webhook client and signature verifier."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.config import get_settings


def eventsub_configured() -> bool:
    settings = get_settings()
    callback = urlparse(settings.twitch_eventsub_callback_url)
    return bool(settings.twitch_client_id and settings.twitch_client_secret and
                10 <= len(settings.twitch_eventsub_secret) <= 100 and
                callback.scheme == "https" and callback.hostname)


def _json_request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=payload, method=method, headers={"Accept": "application/json", "User-Agent": "Klipr.cloud EventSub/1.0", **(headers or {})})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read(1_000_000))


def _app_token() -> str:
    settings = get_settings()
    query = urlencode({"client_id": settings.twitch_client_id, "client_secret": settings.twitch_client_secret, "grant_type": "client_credentials"})
    return _json_request(f"https://id.twitch.tv/oauth2/token?{query}", method="POST")["access_token"]


def register_stream_online(channel_slug: str) -> tuple[str, str] | None:
    if not eventsub_configured():
        return None
    settings, token = get_settings(), _app_token()
    headers = {"Authorization": f"Bearer {token}", "Client-Id": settings.twitch_client_id, "Content-Type": "application/json"}
    user_data = _json_request(f"https://api.twitch.tv/helix/users?{urlencode({'login': channel_slug})}", headers=headers).get("data", [])
    if not user_data:
        raise ValueError("Twitch creator was not found")
    twitch_user_id = str(user_data[0]["id"])
    response = _json_request("https://api.twitch.tv/helix/eventsub/subscriptions", method="POST", headers=headers, body={
        "type": "stream.online", "version": "1", "condition": {"broadcaster_user_id": twitch_user_id},
        "transport": {"method": "webhook", "callback": settings.twitch_eventsub_callback_url, "secret": settings.twitch_eventsub_secret},
    })
    return twitch_user_id, str(response["data"][0]["id"])


def delete_eventsub_subscription(subscription_id: str) -> None:
    if not eventsub_configured() or not subscription_id:
        return
    settings, token = get_settings(), _app_token()
    request = Request(f"https://api.twitch.tv/helix/eventsub/subscriptions?{urlencode({'id': subscription_id})}", method="DELETE", headers={"Authorization": f"Bearer {token}", "Client-Id": settings.twitch_client_id, "User-Agent": "Klipr.cloud EventSub/1.0"})
    with urlopen(request, timeout=10):
        pass


def verify_eventsub_signature(message_id: str, timestamp: str, raw_body: bytes, signature: str, *, max_age_seconds: int = 600) -> bool:
    settings = get_settings()
    if not settings.twitch_eventsub_secret or not all((message_id, timestamp, signature)):
        return False
    try:
        sent_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if abs((datetime.now(timezone.utc) - sent_at).total_seconds()) > max_age_seconds:
            return False
    except ValueError:
        return False
    digest = hmac.new(settings.twitch_eventsub_secret.encode("ascii"), message_id.encode() + timestamp.encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)
