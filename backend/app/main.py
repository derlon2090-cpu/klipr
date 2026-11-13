import base64
import hashlib
import hmac
import json
import secrets
import time
import re
from html import unescape
from urllib.request import HTTPRedirectHandler, Request as UrlRequest, build_opener
from urllib.parse import urlparse, urlunparse
from uuid import UUID
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, text
from app.db import SessionLocal
from app.config import get_settings
from app.models import ArchiveBranding, Clip, Stream, StreamStatus
from app.storage import copy_file, delete_files, presigned_download_url, upload_file
from app.worker.tasks import WORK_ROOT, active_key, record_stream, redis_client, stop_key, task_key

app = FastAPI(title="Klipr.cloud API", description="On-demand creator stream capture and AI clip studio.", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in get_settings().klipr_cors_origins.split(",") if origin.strip()], allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"], allow_credentials=True)


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


def _consume_record_quota(request: Request) -> str:
    """Allow two recording-start requests per client IP per minute."""
    client, key = redis_client(), _client_key(request)
    rate_key, owner_key = f"klipr:record:rate:{key}", f"klipr:record:active:{key}"
    attempts = client.incr(rate_key)
    if attempts == 1:
        client.expire(rate_key, 60)
    if attempts > 2:
        raise HTTPException(429, {"detail": "Recording rate limit exceeded", "retry_after": client.ttl(rate_key)})
    return owner_key


def _reserve_recording_slot(owner_key: str, stream_id: str) -> bool:
    """Atomically reserve one of the two permitted active-recording slots."""
    result = redis_client().eval(
        """
        if redis.call('SCARD', KEYS[1]) >= 2 then return 0 end
        redis.call('SADD', KEYS[1], ARGV[1])
        redis.call('EXPIRE', KEYS[1], 43200)
        return 1
        """,
        1,
        owner_key,
        stream_id,
    )
    return bool(result)


@app.middleware("http")
async def require_klipr_session(request: Request, call_next):
    public_paths = {"/health", "/auth/password", "/auth/email", "/auth/me", "/docs", "/openapi.json"}
    path = request.url.path.removeprefix("/api") or "/"
    if request.method == "OPTIONS" or path in public_paths or _read_token(request.cookies.get("klipr_session"), "session"):
        return await call_next(request)
    return Response(content=json.dumps({"detail": "Authentication required"}), status_code=401, media_type="application/json")

class RecordRequest(BaseModel):
    stream_url: str
    layout_mode: str = "center"
    discord_webhook_url: str | None = None
    custom_headline: str | None = None
    enable_end_screen: bool = True
class PreviewRequest(BaseModel): stream_url: str
class ProcessRequest(BaseModel):
    layout_mode: str | None = None
    discord_webhook_url: str | None = None
    duration_seconds: int | None = None
    max_clips: int = 3
    custom_headline: str | None = None
    embed_intro_cover: bool | None = None
class BrandingRequest(BaseModel):
    enable_end_screen: bool = True
    use_default_thumbnail: bool = True
    outro_duration_seconds: int = 15
    archive_channel_name: str | None = None
    archive_tagline: str | None = None
    default_left_vod_id: UUID | None = None
    default_right_vod_id: UUID | None = None
class PasswordRequest(BaseModel): password: str
class EmailRequest(BaseModel): email: str

WEBHOOK_RE = re.compile(r"^https://(?:discord\.com|discordapp\.com)/api/webhooks/[0-9]+/[A-Za-z0-9_-]+(?:\?.*)?$")

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def safe_urlopen(request: UrlRequest):
    """Metadata fetches never follow a provider redirect to an unvalidated host."""
    return build_opener(_NoRedirect).open(request, timeout=8)

def validate_creator_options(layout_mode: str, webhook: str | None) -> tuple[str, str | None]:
    if layout_mode not in {"center", "split"}:
        raise HTTPException(422, "layout_mode must be center or split")
    if webhook and not WEBHOOK_RE.fullmatch(webhook):
        raise HTTPException(422, "Discord webhook must use the official HTTPS webhook endpoint")
    return layout_mode, webhook

def normalize_live_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise HTTPException(422, "Invalid port") from error
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in {None, 443}:
        raise HTTPException(422, "Only standard HTTPS live URLs are allowed")
    try:
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise HTTPException(422, "Invalid hostname") from error
    platform = "twitch" if host in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"} else "kick" if host in {"kick.com", "www.kick.com"} else None
    if not platform: raise HTTPException(422, "Only Twitch.tv and Kick.com live URLs are supported")
    path = parsed.path.rstrip("/")
    if not path or path == "/": raise HTTPException(422, "A creator channel path is required")
    return platform, urlunparse(("https", host, path, "", "", ""))

def _meta_tag(page: str, property_name: str) -> str | None:
    # Provider page is not trusted markup; return only a bounded, decoded meta value.
    match = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(property_name) + r'["\'][^>]+content=["\']([^"\']+)', page, re.I)
    return unescape(match.group(1)).strip()[:500] if match else None

def preview_stream(platform: str, normalized_url: str) -> dict:
    handle = urlparse(normalized_url).path.strip("/").split("/", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", handle):
        raise HTTPException(422, "Invalid creator channel path")
    try:
        if platform == "kick":
            endpoint = f"https://kick.com/api/v2/channels/{handle}"
            request = UrlRequest(endpoint, headers={"User-Agent": "Klipr.cloud preview/1.0", "Accept": "application/json"})
            with safe_urlopen(request) as response:
                data = json.loads(response.read(1_000_000))
            livestream = data.get("livestream") or {}
            return {"platform": platform, "streamer_name": data.get("user", {}).get("username") or data.get("slug") or handle,
                    "title": livestream.get("session_title") or data.get("stream_title") or "", "live": bool(livestream),
                    "thumbnail_url": livestream.get("thumbnail") or data.get("profile_pic")}
        request = UrlRequest(normalized_url, headers={"User-Agent": "Mozilla/5.0 (compatible; Klipr.cloud preview/1.0)"})
        with safe_urlopen(request) as response:
            page = response.read(1_000_000).decode("utf-8", "replace")
        title = _meta_tag(page, "og:title") or handle
        image = _meta_tag(page, "og:image")
        # Twitch exposes this marker on live channel pages; absent is conservatively offline.
        live = 'isLiveBroadcast' in page or '"isLive":true' in page
        return {"platform": platform, "streamer_name": title.split(" - ")[0][:100], "title": title, "live": live, "thumbnail_url": image}
    except Exception as error:
        raise HTTPException(502, "Could not retrieve live stream metadata") from error

def stream_data(stream: Stream, clips: list[Clip] | None = None) -> dict:
    result = {"id": str(stream.id), "source_url": stream.source_url, "platform": stream.platform, "status": stream.status,
              "master_url": presigned_download_url(stream.master_key) if stream.master_key else None, "started_at": stream.started_at,
              "ended_at": stream.ended_at, "error": stream.error_message, "stop_requested": stream.stop_requested, "layout_mode": stream.layout_mode, "thumbnail_url": presigned_download_url(stream.thumbnail_key) if stream.thumbnail_key else None, "target_clip_duration": stream.target_clip_duration}
    if clips is not None:
        result["clips"] = [{"id": str(c.id), "start_seconds": c.start_seconds, "end_seconds": c.end_seconds, "score": c.score,
                            "transcript": c.transcript, "url": presigned_download_url(c.vertical_key) if c.vertical_key else None, "thumbnail_url": presigned_download_url(c.thumbnail_key) if c.thumbnail_key else None} for c in clips]
    return result

@app.get("/health")
def health(): return {"ok": True}

def _branding(db):
    # Lazy, idempotent upgrade keeps existing deployments compatible without
    # making serverless startup depend on a database connection.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_thumbnail_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS use_default_thumbnail BOOLEAN NOT NULL DEFAULT TRUE"))
        db.commit()
    item = db.get(ArchiveBranding, 1)
    if not item: item = ArchiveBranding(id=1); db.add(item); db.commit(); db.refresh(item)
    return item
@app.get("/branding")
def get_branding():
    with SessionLocal() as db:
        item = _branding(db); return {"enable_end_screen":item.enable_end_screen,"use_default_thumbnail":item.use_default_thumbnail,"outro_duration_seconds":item.outro_duration_seconds,"archive_channel_name":item.archive_channel_name,"archive_tagline":item.archive_tagline,"archive_logo_key":item.archive_logo_key,"archive_logo_url":presigned_download_url(item.archive_logo_key) if item.archive_logo_key else None,"default_thumbnail_key":item.default_thumbnail_key,"default_thumbnail_url":presigned_download_url(item.default_thumbnail_key) if item.default_thumbnail_key else None,"default_left_vod_id":item.default_left_vod_id,"default_right_vod_id":item.default_right_vod_id}
@app.put("/branding")
def put_branding(payload: BrandingRequest):
    if not 10 <= payload.outro_duration_seconds <= 20: raise HTTPException(422,"outro_duration_seconds must be between 10 and 20")
    with SessionLocal() as db:
        item = _branding(db)
        for name, value in payload.model_dump().items(): setattr(item,name,value)
        db.commit()
    return get_branding()
@app.post("/branding/logo")
async def upload_branding_logo(file: UploadFile = File(...)):
    data = await file.read()
    is_png, is_jpg, is_webp = data.startswith(b"\x89PNG\r\n\x1a\n"), data.startswith(b"\xff\xd8\xff"), data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if len(data) > 5*1024*1024 or not (is_png or is_jpg or is_webp): raise HTTPException(422,"Logo must be a PNG, JPG, or WebP under 5MB")
    import tempfile
    suffix = ".png" if is_png else ".jpg" if is_jpg else ".webp"
    key = f"branding/logo_{secrets.token_hex(12)}{suffix}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp: temp.write(data); path = Path(temp.name)
    try:
        upload_file(path,key,"image/png" if suffix==".png" else "image/jpeg")
        with SessionLocal() as db:
            item=_branding(db); old=item.archive_logo_key; item.archive_logo_key=key; db.commit()
        if old: delete_files([old])
    finally: path.unlink(missing_ok=True)
    return {"archive_logo_key":key,"archive_logo_url":presigned_download_url(key)}

@app.delete("/branding/logo", status_code=204)
def delete_branding_logo():
    with SessionLocal() as db:
        item = _branding(db); old = item.archive_logo_key; item.archive_logo_key = None; db.commit()
    if old: delete_files([old])

@app.post("/branding/thumbnail")
async def upload_branding_thumbnail(file: UploadFile = File(...)):
    data = await file.read()
    is_png, is_jpg, is_webp = data.startswith(b"\x89PNG\r\n\x1a\n"), data.startswith(b"\xff\xd8\xff"), data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if len(data) > 8*1024*1024 or not (is_png or is_jpg or is_webp): raise HTTPException(422,"Thumbnail must be a PNG, JPG, or WebP under 8MB")
    import tempfile
    suffix = ".png" if is_png else ".jpg" if is_jpg else ".webp"
    content_type = "image/png" if is_png else "image/jpeg" if is_jpg else "image/webp"
    key = f"branding/thumbnail_{secrets.token_hex(12)}{suffix}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp: temp.write(data); path = Path(temp.name)
    try:
        upload_file(path,key,content_type)
        with SessionLocal() as db:
            item=_branding(db); old=item.default_thumbnail_key; item.default_thumbnail_key=key; item.use_default_thumbnail=True; db.commit()
        if old: delete_files([old])
    finally: path.unlink(missing_ok=True)
    return {"default_thumbnail_key":key,"default_thumbnail_url":presigned_download_url(key),"use_default_thumbnail":True}

@app.delete("/branding/thumbnail", status_code=204)
def delete_branding_thumbnail():
    with SessionLocal() as db:
        item = _branding(db); old = item.default_thumbnail_key; item.default_thumbnail_key = None; item.use_default_thumbnail = False; db.commit()
    if old: delete_files([old])


@app.post("/auth/password")
def verify_password(payload: PasswordRequest, request: Request, response: Response):
    settings = get_settings()
    if not settings.klipr_access_password or not settings.klipr_session_secret:
        raise HTTPException(503, "Authentication is not configured")
    # Authentication must remain available when the optional Redis-backed
    # rate limiter is not configured (for example on a Vercel web function).
    # Recording jobs still require Redis, but password verification does not.
    client = None
    try:
        candidate = redis_client()
        candidate.ping()
        client = candidate
    except Exception:
        pass
    key = _client_key(request)
    lock = f"klipr:auth:lock:{key}"
    if client and client.exists(lock):
        raise HTTPException(429, {"detail": "Too many attempts", "retry_after": client.ttl(lock)})
    if not secrets.compare_digest(payload.password, settings.klipr_access_password):
        if client:
            attempts = client.incr(f"klipr:auth:attempts:{key}")
            client.expire(f"klipr:auth:attempts:{key}", 180)
            if attempts >= 3:
                client.set(lock, "1", ex=180); client.delete(f"klipr:auth:attempts:{key}")
                raise HTTPException(429, {"detail": "Too many attempts", "retry_after": 180})
            raise HTTPException(401, {"detail": "Incorrect password", "remaining": 3 - attempts})
        raise HTTPException(401, "Incorrect password")
    if client:
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
def record(payload: RecordRequest, request: Request):
    platform, normalized = normalize_live_url(payload.stream_url)
    layout_mode, webhook = validate_creator_options(payload.layout_mode, payload.discord_webhook_url)
    owner_key = _consume_record_quota(request)
    client, lock = redis_client(), active_key(normalized)
    if not client.set(lock, "pending", nx=True, ex=43200):
        existing = client.get(lock)
        raise HTTPException(409, {"detail": "This URL is already recording", "stream_id": existing})
    try:
        with SessionLocal() as db:
            branding = _branding(db)
            stream = Stream(channel_id=None, source_url=normalized, platform=platform, status=StreamStatus.queued, layout_mode=layout_mode, discord_webhook_url=webhook, custom_headline=(payload.custom_headline or "").strip()[:160] or None, enable_end_screen=branding.enable_end_screen, archive_channel_name=branding.archive_channel_name, archive_tagline=branding.archive_tagline, outro_duration_seconds=branding.outro_duration_seconds, left_vod_id=branding.default_left_vod_id, right_vod_id=branding.default_right_vod_id)
            db.add(stream); db.flush()
            if branding.default_thumbnail_key and branding.use_default_thumbnail:
                suffix = Path(branding.default_thumbnail_key).suffix or ".png"
                stream.thumbnail_key = f"streams/{stream.id}/custom-thumbnail{suffix}"
                copy_file(branding.default_thumbnail_key, stream.thumbnail_key)
            if branding.archive_logo_key:
                suffix = Path(branding.archive_logo_key).suffix or ".png"
                stream.archive_logo_key = f"streams/{stream.id}/archive-logo{suffix}"
                copy_file(branding.archive_logo_key, stream.archive_logo_key)
            db.commit(); db.refresh(stream)
            if not _reserve_recording_slot(owner_key, str(stream.id)):
                db.delete(stream); db.commit()
                raise HTTPException(429, {"detail": "Maximum of two active recordings reached"})
        client.set(lock, str(stream.id), xx=True, ex=43200)
        task = record_stream.delay(str(stream.id), normalized, owner_key); client.sadd(task_key(str(stream.id)), task.id); client.expire(task_key(str(stream.id)), 43200)
        return stream_data(stream)
    except Exception:
        client.delete(lock)
        if "stream" in locals(): client.srem(owner_key, str(stream.id))
        raise

@app.post("/streams/preview")
def stream_preview(payload: PreviewRequest):
    platform, normalized = normalize_live_url(payload.stream_url)
    return preview_stream(platform, normalized)

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
def process_stream(stream_id: UUID, payload: ProcessRequest = ProcessRequest()):
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        if not stream.master_key: raise HTTPException(409, "The master VOD is not ready")
        if payload.layout_mode is not None or payload.discord_webhook_url is not None:
            layout, webhook = validate_creator_options(payload.layout_mode or stream.layout_mode, payload.discord_webhook_url)
            stream.layout_mode = layout
            if payload.discord_webhook_url is not None: stream.discord_webhook_url = webhook
        if payload.duration_seconds is not None:
            if not 10 <= payload.duration_seconds <= 180: raise HTTPException(422, "duration_seconds must be between 10 and 180")
            stream.target_clip_duration = payload.duration_seconds
        if not 1 <= payload.max_clips <= 10: raise HTTPException(422, "max_clips must be between 1 and 10")
        if payload.custom_headline is not None: stream.custom_headline = payload.custom_headline.strip()[:160] or None
        if payload.embed_intro_cover is not None: stream.embed_intro_cover = payload.embed_intro_cover
        db.commit()
    # Keep the Vercel API package lean; the Whisper worker imports this only in its own container.
    from app.worker.highlights import process_stream_highlights
    task = process_stream_highlights.delay(str(stream_id), payload.max_clips)
    redis_client().sadd(task_key(str(stream_id)), task.id); redis_client().expire(task_key(str(stream_id)), 43200)
    return {"id": str(stream_id), "status": StreamStatus.processing}

@app.post("/recordings/{stream_id}/clips/generate", status_code=202)
def generate_custom_clips(stream_id: UUID, payload: ProcessRequest):
    return process_stream(stream_id, payload)

@app.delete("/recordings/{stream_id}", status_code=204)
def delete_recording(stream_id: UUID):
    """Irreversible purge of task state, R2 media, local scratch and DB metadata."""
    sid = str(stream_id)
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        clips = db.query(Clip).filter(Clip.stream_id == stream_id).all()
        keys = [key for key in [stream.master_key, stream.thumbnail_key, stream.archive_logo_key] + [value for clip in clips for value in (clip.vertical_key, clip.thumbnail_key, clip.captions_key)] if key]
        source_url = stream.source_url
        try:
            from app.worker.celery_app import celery_app
            for task_id in redis_client().smembers(task_key(sid)): celery_app.control.revoke(task_id, terminate=True)
        finally:
            client = redis_client(); client.set(stop_key(sid), "1", ex=300); client.delete(active_key(source_url), task_key(sid))
        try: delete_files(keys)
        finally:
            import shutil
            shutil.rmtree(WORK_ROOT / sid, ignore_errors=True)
            db.delete(stream); db.commit()
