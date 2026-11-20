"""Authenticated, redacted Session Vault endpoints."""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.core.crypto import encrypt_secret
from app.db import SessionLocal
from app.models import Notification, SessionCredential

router = APIRouter(prefix="/credentials", tags=["credentials"])
PLATFORMS = {"kick", "twitch"}
COOKIE_EXPIRY = re.compile(r"^(?:#HttpOnly_)?[^\t]+\t(?:TRUE|FALSE)\t/[^\t]*\t(?:TRUE|FALSE)\t(\d+)\t", re.M)


class SessionPayload(BaseModel):
    content: str = Field(min_length=1, max_length=65536)

    @field_validator("content")
    @classmethod
    def content_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Session content cannot be empty")
        return value


def extract_cookie_expiry(content: str) -> datetime | None:
    """Earliest non-session expiry in a Netscape cookies.txt payload."""
    values = [int(value) for value in COOKIE_EXPIRY.findall(content) if int(value) > 0]
    return datetime.fromtimestamp(min(values), tz=timezone.utc) if values else None


def _ensure_schema(db) -> None:
    if db.bind.dialect.name == "postgresql":
        db.execute(text("CREATE TABLE IF NOT EXISTS session_credentials (platform VARCHAR(16) PRIMARY KEY, session_encrypted TEXT, status VARCHAR(16) NOT NULL DEFAULT 'unset', updated_at TIMESTAMPTZ, expires_at TIMESTAMPTZ, CONSTRAINT session_credentials_platform CHECK (platform IN ('kick','twitch')), CONSTRAINT session_credentials_status CHECK (status IN ('active','expiring_soon','expired','unset')))"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS auto_trim_ads BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notification_status_check"))
        db.execute(text("ALTER TABLE notifications ADD CONSTRAINT notification_status_check CHECK (status IN ('pending_auto_record','auto_started','cancelled','manual_taken_over','session_expired'))"))
        db.commit()


def public_credential(item: SessionCredential | None, platform: str) -> dict:
    status = item.status if item else "unset"
    expires = item.expires_at if item else None
    if status == "active" and expires and expires <= datetime.now(timezone.utc):
        status = "expired"
    return {"platform": platform, "has_session": bool(item and item.session_encrypted), "status": status, "updated_at": item.updated_at if item else None, "expires_at": expires}


@router.get("")
def get_credentials():
    with SessionLocal() as db:
        _ensure_schema(db)
        return {platform: public_credential(db.get(SessionCredential, platform), platform) for platform in sorted(PLATFORMS)}


@router.get("/{platform}")
def get_credential(platform: str):
    if platform not in PLATFORMS: raise HTTPException(404, "Unknown platform")
    with SessionLocal() as db:
        _ensure_schema(db)
        return public_credential(db.get(SessionCredential, platform), platform)


@router.put("/{platform}")
def put_credential(platform: str, payload: SessionPayload):
    if platform not in PLATFORMS: raise HTTPException(404, "Unknown platform")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        _ensure_schema(db)
        item = db.get(SessionCredential, platform) or SessionCredential(platform=platform)
        item.session_encrypted = encrypt_secret(payload.content)
        item.status, item.updated_at, item.expires_at = "active", now, extract_cookie_expiry(payload.content)
        db.add(item)
        # Clear obsolete expiry alerts without ever querying secret material.
        db.query(Notification).filter(Notification.status == "session_expired", Notification.channel_url == f"session://{platform}").update({"is_read": True})
        db.commit(); db.refresh(item)
        return public_credential(item, platform)


@router.delete("/{platform}", status_code=204)
def delete_credential(platform: str):
    if platform not in PLATFORMS: raise HTTPException(404, "Unknown platform")
    with SessionLocal() as db:
        _ensure_schema(db)
        item = db.get(SessionCredential, platform) or SessionCredential(platform=platform)
        item.session_encrypted = None
        item.status, item.updated_at, item.expires_at = "unset", datetime.now(timezone.utc), None
        db.add(item); db.commit()
