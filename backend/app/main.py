import base64
import hashlib
import hmac
import json
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse
from uuid import UUID
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel
from sqlalchemy import func
from app.db import Base, engine, SessionLocal
from app.config import get_settings
from app.models import Clip, Stream, StreamStatus
from app.storage import presigned_download_url
from app.worker.tasks import active_key, record_stream, redis_client, stop_key

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Klipr.cloud API", description="On-demand creator stream capture and AI clip studio.", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)


@app.middleware("http")
async def strip_vercel_api_prefix(request, call_next):
    """Vercel Services routes /api/* to this app while local Docker keeps direct paths."""
    if request.scope["path"].startswith("/api/"):
        request.scope["path"] = request.scope["path"][4:] or "/"
    return await call_next(request)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _token(payload: dict) -> str:
    secret = get_settings().klipr_session_secret.encode()
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(secret, encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _read_token(value: str | None, kind: str) -> dict | None:
    if not value or not get_settings().klipr_session_secret:
        return None
    try:
        encoded, signature = value.split(".", 1)
        expected = _b64(hmac.new(get_settings().klipr_session_secret.encode(), encoded.encode(), hashlib.sha256).digest())
        payload = json.loads(_unb64(encoded))
        return payload if hmac.compare_digest(signature, expected) and payload.get("kind") == kind and payload.get("exp", 0) > time.time() else None
    except (ValueError, json.JSONDecodeError):
        return None


def _client_key(request: Request) -> str:
    address = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    return hashlib.sha256(address.encode()).hexdigest()


@app.middleware("http")
async def require_klipr_session(request: Request, call_next):
    public_paths = {"/health", "/auth/password", "/auth/email", "/auth/me", "/docs", "/openapi.json"}
    path = request.url.path.removeprefix("/api") or "/"
    if request.method == "OPTIONS" or path in public_paths or _read_token(request.cookies.get("klipr_session"), "session"):
        return await call_next(request)
    return Response(content=json.dumps({"detail": "Authentication required"}), status_code=401, media_type="application/json")

class RecordRequest(BaseModel): stream_url: AnyHttpUrl
class PasswordRequest(BaseModel): password: str
class EmailRequest(BaseModel): email: str

def normalize_live_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    platform = "twitch" if host in {"twitch.tv", "m.twitch.tv"} or host.endswith(".twitch.tv") else "kick" if host == "kick.com" or host.endswith(".kick.com") else None
    if not platform: raise HTTPException(422, "Only live Twitch and Kick URLs are supported")
    path = parsed.path.rstrip("/")
    if not path or path == "/": raise HTTPException(422, "A creator channel path is required")
    return platform, urlunparse(("https", host, path, "", "", ""))

def stream_data(stream: Stream, clips: list[Clip] | None = None) -> dict:
    result = {"id": str(stream.id), "source_url": stream.source_url, "platform": stream.platform, "status": stream.status,
              "master_url": presigned_download_url(stream.master_key) if stream.master_key else None, "started_at": stream.started_at,
              "ended_at": stream.ended_at, "error": stream.error_message, "stop_requested": stream.stop_requested}
    if clips is not None:
        result["clips"] = [{"id": str(c.id), "start_seconds": c.start_seconds, "end_seconds": c.end_seconds, "score": c.score,
                            "transcript": c.transcript, "url": presigned_download_url(c.vertical_key) if c.vertical_key else None} for c in clips]
    return result

@app.get("/health")
def health(): return {"ok": True}


@app.post("/auth/password")
def verify_password(payload: PasswordRequest, request: Request, response: Response):
    settings = get_settings()
    if not settings.klipr_access_password or not settings.klipr_session_secret:
        raise HTTPException(503, "Authentication is not configured")
    client, key = redis_client(), _client_key(request)
    lock = f"klipr:auth:lock:{key}"
    if client.exists(lock):
        raise HTTPException(429, {"detail": "Too many attempts", "retry_after": client.ttl(lock)})
    if not secrets.compare_digest(payload.password, settings.klipr_access_password):
        attempts = client.incr(f"klipr:auth:attempts:{key}")
        client.expire(f"klipr:auth:attempts:{key}", 180)
        if attempts >= 3:
            client.set(lock, "1", ex=180); client.delete(f"klipr:auth:attempts:{key}")
            raise HTTPException(429, {"detail": "Too many attempts", "retry_after": 180})
        raise HTTPException(401, {"detail": "Incorrect password", "remaining": 3 - attempts})
    client.delete(f"klipr:auth:attempts:{key}")
    response.set_cookie("klipr_ticket", _token({"kind": "ticket", "exp": time.time() + 600}), httponly=True, secure=settings.klipr_secure_cookies, samesite="lax", max_age=600, path="/")
    return {"next": "email"}


@app.post("/auth/email")
def verify_email(payload: EmailRequest, request: Request, response: Response):
    settings = get_settings()
    if not _read_token(request.cookies.get("klipr_ticket"), "ticket"):
        raise HTTPException(401, "Password verification expired")
    if payload.email.strip().lower() != settings.klipr_allowed_email.lower():
        raise HTTPException(403, "This email is not authorized")
    response.delete_cookie("klipr_ticket", path="/")
    response.set_cookie("klipr_session", _token({"kind": "session", "email": settings.klipr_allowed_email, "exp": time.time() + 60 * 60 * 12}), httponly=True, secure=settings.klipr_secure_cookies, samesite="lax", max_age=60 * 60 * 12, path="/")
    return {"email": settings.klipr_allowed_email}


@app.get("/auth/me")
def auth_me(request: Request):
    session = _read_token(request.cookies.get("klipr_session"), "session")
    if not session: raise HTTPException(401, "Authentication required")
    return {"email": session["email"]}


@app.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("klipr_session", path="/")

@app.post("/streams/record", status_code=202)
def record(payload: RecordRequest):
    platform, normalized = normalize_live_url(str(payload.stream_url))
    client, lock = redis_client(), active_key(normalized)
    if not client.set(lock, "pending", nx=True, ex=43200):
        existing = client.get(lock)
        raise HTTPException(409, {"detail": "This URL is already recording", "stream_id": existing})
    try:
        with SessionLocal() as db:
            stream = Stream(channel_id=None, source_url=normalized, platform=platform, status=StreamStatus.queued)
            db.add(stream); db.commit(); db.refresh(stream)
        client.set(lock, str(stream.id), xx=True, ex=43200)
        record_stream.delay(str(stream.id), normalized)
        return stream_data(stream)
    except Exception:
        client.delete(lock)
        raise

@app.get("/streams")
def list_streams():
    with SessionLocal() as db:
        streams = db.query(Stream).order_by(Stream.created_at.desc()).all()
        counts = dict(db.query(Clip.stream_id, func.count(Clip.id)).group_by(Clip.stream_id).all())
        return [{**stream_data(stream), "clip_count": counts.get(stream.id, 0)} for stream in streams]

@app.get("/streams/{stream_id}")
def stream_status(stream_id: UUID):
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        clips = db.query(Clip).filter(Clip.stream_id == stream_id).order_by(Clip.start_seconds).all()
        return stream_data(stream, clips)

@app.post("/streams/{stream_id}/stop", status_code=202)
def stop_recording(stream_id: UUID):
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        if stream.status not in {StreamStatus.queued, StreamStatus.recording, StreamStatus.reconnecting}:
            raise HTTPException(409, "This stream is not actively recording")
        stream.stop_requested = True; db.commit()
    redis_client().set(stop_key(str(stream_id)), "1", ex=300)
    return {"id": str(stream_id), "status": "stopping"}

@app.post("/streams/{stream_id}/process", status_code=202)
def process_stream(stream_id: UUID):
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        if not stream.master_key: raise HTTPException(409, "The master VOD is not ready")
    # Keep the Vercel API package lean; the Whisper worker imports this only in its own container.
    from app.worker.highlights import process_stream_highlights
    process_stream_highlights.delay(str(stream_id))
    return {"id": str(stream_id), "status": StreamStatus.processing}
