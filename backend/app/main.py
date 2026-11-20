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
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, text
from app.db import Base, SessionLocal, engine
from app.migrations import apply_migrations
from app.config import get_settings
from app.models import ArchiveBranding, Clip, CreatorSuggestion, Notification, SavedThumbnail, Stream, StreamStatus, WatchlistSubscription
from app.storage import copy_file, delete_files, presigned_download_url, upload_file
from app.worker.tasks import WORK_ROOT, active_key, record_stream, redis_client, stop_key, task_key
from app.api.credentials import router as credentials_router

app = FastAPI(title="Klipr.cloud API", description="On-demand creator stream capture and AI clip studio.", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in get_settings().klipr_cors_origins.split(",") if origin.strip()], allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"], allow_credentials=True)
app.include_router(credentials_router)


@app.on_event("startup")
def initialize_database() -> None:
    """Create the current schema, then apply versioned upgrades for existing DBs."""
    if engine is None:
        return
    Base.metadata.create_all(bind=engine)
    apply_migrations(engine)


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
    public_paths = {"/health", "/auth/password", "/auth/email", "/auth/me", "/webhooks/twitch/eventsub", "/docs", "/openapi.json"}
    path = request.url.path.removeprefix("/api") or "/"
    public_suggestion = path == "/creator-suggestions" and request.method == "POST"
    if request.method == "OPTIONS" or path in public_paths or public_suggestion or _read_token(request.cookies.get("klipr_session"), "session"):
        return await call_next(request)
    return Response(content=json.dumps({"detail": "Authentication required"}), status_code=401, media_type="application/json")

class RecordRequest(BaseModel):
    stream_url: str
    layout_mode: str = "center"
    discord_webhook_url: str | None = None
    custom_headline: str | None = None
    enable_end_screen: bool = True
    remove_music: bool | None = None
class PreviewRequest(BaseModel): stream_url: str
class ProcessRequest(BaseModel):
    layout_mode: str | None = None
    discord_webhook_url: str | None = None
    duration_seconds: int | None = None
    max_clips: int = 3
    custom_headline: str | None = None
    embed_intro_cover: bool | None = None
    remove_music: bool | None = None
class BrandingRequest(BaseModel):
    enable_end_screen: bool = True
    remove_music: bool = False
    auto_trim_ads: bool = False
    use_default_thumbnail: bool = True
    outro_duration_seconds: int = 15
    archive_channel_name: str | None = None
    archive_tagline: str | None = None
    default_left_vod_id: UUID | None = None
    default_right_vod_id: UUID | None = None
class WatchlistRequest(BaseModel):
    channel_url: str
    auto_record: bool = True
    delay_seconds: int = 30
class WatchlistPatch(BaseModel):
    auto_record: bool | None = None
    delay_seconds: int | None = None
class CreatorSuggestionRequest(BaseModel):
    creator_name: str = Field(min_length=2, max_length=120)
    platform: str
    channel_url: str | None = Field(default=None, max_length=500)

    @field_validator("creator_name")
    @classmethod
    def clean_creator_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Creator name is too short")
        return cleaned

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        platform = value.strip().lower()
        if platform not in {"twitch", "kick"}:
            raise ValueError("Platform must be Twitch or Kick")
        return platform

class CreatorSuggestionPatch(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"new", "reviewed"}:
            raise ValueError("Status must be new or reviewed")
        return value
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
                    "thumbnail_url": livestream.get("thumbnail") or data.get("profile_pic"), "stream_id": str(livestream.get("id")) if livestream.get("id") else None}
        request = UrlRequest(normalized_url, headers={"User-Agent": "Mozilla/5.0 (compatible; Klipr.cloud preview/1.0)"})
        with safe_urlopen(request) as response:
            page = response.read(1_000_000).decode("utf-8", "replace")
        title = _meta_tag(page, "og:title") or handle
        image = _meta_tag(page, "og:image")
        # Twitch exposes this marker on live channel pages; absent is conservatively offline.
        live = 'isLiveBroadcast' in page or '"isLive":true' in page
        marker = hashlib.sha256(f"{title}|{image or ''}".encode()).hexdigest()[:32] if live else None
        return {"platform": platform, "streamer_name": title.split(" - ")[0][:100], "title": title, "live": live, "thumbnail_url": image, "stream_id": marker}
    except Exception as error:
        raise HTTPException(502, "Could not retrieve live stream metadata") from error

def stream_data(stream: Stream, clips: list[Clip] | None = None) -> dict:
    result = {"id": str(stream.id), "source_url": stream.source_url, "platform": stream.platform, "status": stream.status,
              "master_url": presigned_download_url(stream.master_key) if stream.master_key else None, "started_at": stream.started_at,
              "ended_at": stream.ended_at, "error": stream.error_message, "stop_requested": stream.stop_requested, "layout_mode": stream.layout_mode, "remove_music": stream.remove_music, "thumbnail_url": presigned_download_url(stream.thumbnail_key) if stream.thumbnail_key else None, "target_clip_duration": stream.target_clip_duration}
    if clips is not None:
        result["clips"] = [{"id": str(c.id), "start_seconds": c.start_seconds, "end_seconds": c.end_seconds, "score": c.score,
                            "viral_score":c.viral_score,"hook_title":c.hook_title,"highlight_reason":c.highlight_reason,"transcript_snippet":c.transcript_snippet or c.transcript,
                            "transcript": c.transcript, "url": presigned_download_url(c.vertical_key) if c.vertical_key else None, "thumbnail_url": presigned_download_url(c.thumbnail_key) if c.thumbnail_key else None} for c in clips]
    return result

@app.get("/health")
def health(): return {"ok": True}

def _ensure_preset_schema(db):
    # Lazy, idempotent upgrade keeps existing deployments compatible without
    # making serverless startup depend on a database connection.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_thumbnail_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_short_thumbnail_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS use_default_thumbnail BOOLEAN NOT NULL DEFAULT TRUE"))
        db.execute(text("ALTER TABLE streams ADD COLUMN IF NOT EXISTS short_thumbnail_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS remove_music BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS auto_trim_ads BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("ALTER TABLE streams ADD COLUMN IF NOT EXISTS remove_music BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("CREATE TABLE IF NOT EXISTS saved_thumbnails (id UUID PRIMARY KEY, kind VARCHAR(16) NOT NULL, storage_key TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT saved_thumbnails_kind_check CHECK (kind IN ('vod', 'short')))"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_saved_thumbnails_kind ON saved_thumbnails(kind)"))
        db.execute(text("ALTER TABLE clips ADD COLUMN IF NOT EXISTS viral_score INTEGER NOT NULL DEFAULT 0"))
        db.execute(text("ALTER TABLE clips ADD COLUMN IF NOT EXISTS hook_title VARCHAR(160)"))
        db.execute(text("ALTER TABLE clips ADD COLUMN IF NOT EXISTS highlight_reason VARCHAR(120)"))
        db.execute(text("ALTER TABLE clips ADD COLUMN IF NOT EXISTS transcript_snippet TEXT"))
        db.commit()

def _ensure_watchlist_schema(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("CREATE TABLE IF NOT EXISTS watchlist_subscriptions (id UUID PRIMARY KEY, platform VARCHAR(16) NOT NULL, channel_slug VARCHAR(100) NOT NULL, channel_url TEXT NOT NULL UNIQUE, display_name VARCHAR(120) NOT NULL, avatar_url TEXT, auto_record BOOLEAN NOT NULL DEFAULT TRUE, delay_seconds INTEGER NOT NULL DEFAULT 30, is_currently_live BOOLEAN NOT NULL DEFAULT FALSE, last_stream_id VARCHAR(255), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT watchlist_platform_check CHECK (platform IN ('twitch','kick')), CONSTRAINT watchlist_delay_check CHECK (delay_seconds BETWEEN 10 AND 300))"))
        db.execute(text("CREATE TABLE IF NOT EXISTS notifications (id UUID PRIMARY KEY, subscription_id UUID REFERENCES watchlist_subscriptions(id) ON DELETE SET NULL, title VARCHAR(200) NOT NULL, message TEXT NOT NULL, channel_url TEXT NOT NULL, status VARCHAR(32) NOT NULL, is_read BOOLEAN NOT NULL DEFAULT FALSE, scheduled_for TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT notification_status_check CHECK (status IN ('pending_auto_record','auto_started','cancelled','manual_taken_over')))"))
        db.execute(text("ALTER TABLE watchlist_subscriptions ADD COLUMN IF NOT EXISTS twitch_user_id VARCHAR(64)"))
        db.execute(text("ALTER TABLE watchlist_subscriptions ADD COLUMN IF NOT EXISTS eventsub_subscription_id VARCHAR(255)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications(created_at DESC)"))
        db.commit()

def _ensure_suggestions_schema(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("CREATE TABLE IF NOT EXISTS creator_suggestions (id UUID PRIMARY KEY, creator_name VARCHAR(120) NOT NULL, platform VARCHAR(16) NOT NULL, channel_url TEXT, status VARCHAR(16) NOT NULL DEFAULT 'new', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), CONSTRAINT creator_suggestions_platform_check CHECK (platform IN ('twitch','kick')), CONSTRAINT creator_suggestions_status_check CHECK (status IN ('new','reviewed')))"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_creator_suggestions_status_created ON creator_suggestions(status, created_at DESC)"))
        db.commit()

def _suggestion_data(item: CreatorSuggestion) -> dict:
    return {"id": str(item.id), "creator_name": item.creator_name, "platform": item.platform, "channel_url": item.channel_url, "status": item.status, "created_at": item.created_at}

@app.post("/creator-suggestions", status_code=201)
def create_creator_suggestion(payload: CreatorSuggestionRequest):
    channel_url = (payload.channel_url or "").strip() or None
    if channel_url:
        platform, channel_url = normalize_live_url(channel_url)
        if platform != payload.platform:
            raise HTTPException(422, "Channel URL does not match the selected platform")
    with SessionLocal() as db:
        _ensure_suggestions_schema(db)
        item = CreatorSuggestion(creator_name=payload.creator_name, platform=payload.platform, channel_url=channel_url, status="new")
        db.add(item); db.commit(); db.refresh(item)
        return _suggestion_data(item)

@app.get("/creator-suggestions")
def list_creator_suggestions():
    with SessionLocal() as db:
        _ensure_suggestions_schema(db)
        items = db.query(CreatorSuggestion).order_by(CreatorSuggestion.created_at.desc()).all()
        return [_suggestion_data(item) for item in items]

@app.patch("/creator-suggestions/{suggestion_id}")
def update_creator_suggestion(suggestion_id: UUID, payload: CreatorSuggestionPatch):
    with SessionLocal() as db:
        _ensure_suggestions_schema(db)
        item = db.get(CreatorSuggestion, suggestion_id)
        if item is None: raise HTTPException(404, "Suggestion not found")
        item.status = payload.status; db.commit(); db.refresh(item)
        return _suggestion_data(item)

@app.delete("/creator-suggestions/{suggestion_id}", status_code=204)
def delete_creator_suggestion(suggestion_id: UUID):
    with SessionLocal() as db:
        _ensure_suggestions_schema(db)
        item = db.get(CreatorSuggestion, suggestion_id)
        if item is None: raise HTTPException(404, "Suggestion not found")
        db.delete(item); db.commit()
def _branding(db):
    _ensure_preset_schema(db)
    item = db.get(ArchiveBranding, 1)
    if not item: item = ArchiveBranding(id=1); db.add(item); db.commit(); db.refresh(item)
    return item
@app.get("/branding")
def get_branding():
    with SessionLocal() as db:
        item = _branding(db); return {"enable_end_screen":item.enable_end_screen,"remove_music":item.remove_music,"auto_trim_ads":item.auto_trim_ads,"use_default_thumbnail":item.use_default_thumbnail,"outro_duration_seconds":item.outro_duration_seconds,"archive_channel_name":item.archive_channel_name,"archive_tagline":item.archive_tagline,"archive_logo_key":item.archive_logo_key,"archive_logo_url":presigned_download_url(item.archive_logo_key) if item.archive_logo_key else None,"default_thumbnail_key":item.default_thumbnail_key,"default_thumbnail_url":presigned_download_url(item.default_thumbnail_key) if item.default_thumbnail_key else None,"default_short_thumbnail_key":item.default_short_thumbnail_key,"default_short_thumbnail_url":presigned_download_url(item.default_short_thumbnail_key) if item.default_short_thumbnail_key else None,"default_left_vod_id":item.default_left_vod_id,"default_right_vod_id":item.default_right_vod_id}
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
async def upload_branding_thumbnail(file: UploadFile = File(...), kind: str = Form("vod")):
    if kind not in {"vod", "short"}: raise HTTPException(422,"kind must be vod or short")
    data = await file.read()
    is_png, is_jpg, is_webp = data.startswith(b"\x89PNG\r\n\x1a\n"), data.startswith(b"\xff\xd8\xff"), data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if len(data) > 8*1024*1024 or not (is_png or is_jpg or is_webp): raise HTTPException(422,"Thumbnail must be a PNG, JPG, or WebP under 8MB")
    import tempfile
    suffix = ".png" if is_png else ".jpg" if is_jpg else ".webp"
    content_type = "image/png" if is_png else "image/jpeg" if is_jpg else "image/webp"
    key = f"branding/{kind}_thumbnail_{secrets.token_hex(12)}{suffix}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp: temp.write(data); path = Path(temp.name)
    try:
        upload_file(path,key,content_type)
        with SessionLocal() as db:
            item=_branding(db)
            field = "default_short_thumbnail_key" if kind == "short" else "default_thumbnail_key"
            old=getattr(item, field); setattr(item, field, key)
            if kind == "vod": item.use_default_thumbnail=True
            db.add(SavedThumbnail(kind=kind, storage_key=key))
            db.commit()
    finally: path.unlink(missing_ok=True)
    return {"kind":kind,"key":key,"url":presigned_download_url(key),"use_default_thumbnail":item.use_default_thumbnail}

@app.get("/branding/thumbnails")
def list_saved_thumbnails():
    with SessionLocal() as db:
        item = _branding(db)
        # Preserve presets created before the gallery feature was introduced.
        for kind, key in (("vod", item.default_thumbnail_key), ("short", item.default_short_thumbnail_key)):
            if key and not db.query(SavedThumbnail).filter(SavedThumbnail.storage_key == key).first():
                db.add(SavedThumbnail(kind=kind, storage_key=key))
        db.commit()
        rows = db.query(SavedThumbnail).order_by(SavedThumbnail.created_at.desc()).all()
        return [{"id":str(row.id),"kind":row.kind,"key":row.storage_key,"url":presigned_download_url(row.storage_key),"selected":row.storage_key == (item.default_short_thumbnail_key if row.kind == "short" else item.default_thumbnail_key)} for row in rows]

@app.post("/branding/thumbnails/{thumbnail_id}/select")
def select_saved_thumbnail(thumbnail_id: UUID):
    with SessionLocal() as db:
        item, thumbnail = _branding(db), db.get(SavedThumbnail, thumbnail_id)
        if thumbnail is None: raise HTTPException(404, "Saved thumbnail not found")
        if thumbnail.kind == "short": item.default_short_thumbnail_key = thumbnail.storage_key
        else: item.default_thumbnail_key = thumbnail.storage_key; item.use_default_thumbnail = True
        db.commit()
        return {"id":str(thumbnail.id),"kind":thumbnail.kind,"key":thumbnail.storage_key,"url":presigned_download_url(thumbnail.storage_key),"selected":True}

@app.delete("/branding/thumbnails/{thumbnail_id}", status_code=204)
def delete_saved_thumbnail(thumbnail_id: UUID):
    with SessionLocal() as db:
        item, thumbnail = _branding(db), db.get(SavedThumbnail, thumbnail_id)
        if thumbnail is None: raise HTTPException(404, "Saved thumbnail not found")
        key = thumbnail.storage_key
        if item.default_thumbnail_key == key: item.default_thumbnail_key = None; item.use_default_thumbnail = False
        if item.default_short_thumbnail_key == key: item.default_short_thumbnail_key = None
        db.delete(thumbnail); db.commit()
    delete_files([key])

@app.delete("/branding/thumbnail", status_code=204)
def delete_branding_thumbnail(kind: str = "vod"):
    if kind not in {"vod", "short"}: raise HTTPException(422,"kind must be vod or short")
    with SessionLocal() as db:
        item = _branding(db); field = "default_short_thumbnail_key" if kind == "short" else "default_thumbnail_key"; old = getattr(item, field); setattr(item, field, None)
        if kind == "vod": item.use_default_thumbnail = False
        if old: db.query(SavedThumbnail).filter(SavedThumbnail.storage_key == old).delete()
        db.commit()
    if old: delete_files([old])

async def _validated_thumbnail(file: UploadFile) -> tuple[bytes, str, str]:
    """Accept only bounded image uploads before sending them to object storage."""
    data = await file.read()
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpg = data.startswith(b"\xff\xd8\xff")
    is_webp = data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if len(data) > 8 * 1024 * 1024 or not (is_png or is_jpg or is_webp):
        raise HTTPException(422, "Thumbnail must be a PNG, JPG, or WebP under 8MB")
    return data, ".png" if is_png else ".jpg" if is_jpg else ".webp", "image/png" if is_png else "image/jpeg" if is_jpg else "image/webp"

@app.post("/recordings/{stream_id}/thumbnail")
async def upload_recording_thumbnail(stream_id: UUID, file: UploadFile = File(...)):
    data, suffix, content_type = await _validated_thumbnail(file)
    import tempfile
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        old = stream.thumbnail_key
        key = f"streams/{stream_id}/custom-thumbnail-{secrets.token_hex(8)}{suffix}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp: temp.write(data); path = Path(temp.name)
        try:
            upload_file(path, key, content_type)
            stream.thumbnail_key = key; db.commit()
        finally:
            path.unlink(missing_ok=True)
    if old: delete_files([old])
    return {"key": key, "url": presigned_download_url(key)}

@app.post("/clips/{clip_id}/thumbnail")
async def upload_clip_thumbnail(clip_id: UUID, file: UploadFile = File(...)):
    data, suffix, content_type = await _validated_thumbnail(file)
    import tempfile
    with SessionLocal() as db:
        clip = db.get(Clip, clip_id)
        if clip is None: raise HTTPException(404, "Clip not found")
        old = clip.thumbnail_key
        key = f"clips/{clip.stream_id}/custom-thumbnail-{clip_id}-{secrets.token_hex(8)}{suffix}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp: temp.write(data); path = Path(temp.name)
        try:
            upload_file(path, key, content_type)
            clip.thumbnail_key = key; db.commit()
        finally:
            path.unlink(missing_ok=True)
    if old: delete_files([old])
    return {"key": key, "url": presigned_download_url(key)}


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
            stream = Stream(channel_id=None, source_url=normalized, platform=platform, status=StreamStatus.queued, layout_mode=layout_mode, discord_webhook_url=webhook, custom_headline=(payload.custom_headline or "").strip()[:160] or None, enable_end_screen=branding.enable_end_screen, remove_music=branding.remove_music if payload.remove_music is None else payload.remove_music, archive_channel_name=branding.archive_channel_name, archive_tagline=branding.archive_tagline, outro_duration_seconds=branding.outro_duration_seconds, left_vod_id=branding.default_left_vod_id, right_vod_id=branding.default_right_vod_id)
            db.add(stream); db.flush()
            if branding.default_thumbnail_key and branding.use_default_thumbnail:
                suffix = Path(branding.default_thumbnail_key).suffix or ".png"
                stream.thumbnail_key = f"streams/{stream.id}/custom-thumbnail{suffix}"
                copy_file(branding.default_thumbnail_key, stream.thumbnail_key)
            if branding.archive_logo_key:
                suffix = Path(branding.archive_logo_key).suffix or ".png"
                stream.archive_logo_key = f"streams/{stream.id}/archive-logo{suffix}"
                copy_file(branding.archive_logo_key, stream.archive_logo_key)
            if branding.default_short_thumbnail_key:
                suffix = Path(branding.default_short_thumbnail_key).suffix or ".png"
                stream.short_thumbnail_key = f"streams/{stream.id}/short-thumbnail{suffix}"
                copy_file(branding.default_short_thumbnail_key, stream.short_thumbnail_key)
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

def _watchlist_data(item: WatchlistSubscription) -> dict:
    return {"id":str(item.id),"platform":item.platform,"channel_slug":item.channel_slug,"channel_url":item.channel_url,"display_name":item.display_name,"avatar_url":item.avatar_url,"auto_record":item.auto_record,"delay_seconds":item.delay_seconds,"is_currently_live":item.is_currently_live,"created_at":item.created_at}

def _notification_data(item: Notification) -> dict:
    return {"id":str(item.id),"subscription_id":str(item.subscription_id) if item.subscription_id else None,"title":item.title,"message":item.message,"channel_url":item.channel_url,"status":item.status,"is_read":item.is_read,"scheduled_for":item.scheduled_for,"created_at":item.created_at}

@app.get("/watchlist")
def list_watchlist():
    with SessionLocal() as db:
        _ensure_watchlist_schema(db)
        return [_watchlist_data(item) for item in db.query(WatchlistSubscription).order_by(WatchlistSubscription.created_at.desc()).all()]

@app.post("/watchlist", status_code=201)
def add_watchlist(payload: WatchlistRequest):
    if not 10 <= payload.delay_seconds <= 300: raise HTTPException(422, "delay_seconds must be between 10 and 300")
    platform, normalized = normalize_live_url(payload.channel_url)
    metadata = preview_stream(platform, normalized)
    slug = urlparse(normalized).path.strip("/").split("/", 1)[0]
    with SessionLocal() as db:
        _ensure_watchlist_schema(db)
        if db.query(WatchlistSubscription).filter(WatchlistSubscription.channel_url == normalized).first(): raise HTTPException(409, "Creator is already subscribed")
        twitch_user_id = eventsub_id = None
        if platform == "twitch":
            try:
                from app.twitch_eventsub import register_stream_online
                registration = register_stream_online(slug)
                if registration: twitch_user_id, eventsub_id = registration
            except Exception:
                # Keep a polling fallback if credentials or Twitch are temporarily unavailable.
                pass
        item = WatchlistSubscription(platform=platform, channel_slug=slug, channel_url=normalized, display_name=metadata.get("streamer_name") or slug, avatar_url=metadata.get("thumbnail_url"), auto_record=payload.auto_record, delay_seconds=payload.delay_seconds, is_currently_live=False, last_stream_id=None, twitch_user_id=twitch_user_id, eventsub_subscription_id=eventsub_id)
        db.add(item); db.commit(); db.refresh(item)
        return _watchlist_data(item)

@app.patch("/watchlist/{subscription_id}")
def update_watchlist(subscription_id: UUID, payload: WatchlistPatch):
    if payload.delay_seconds is not None and not 10 <= payload.delay_seconds <= 300: raise HTTPException(422, "delay_seconds must be between 10 and 300")
    with SessionLocal() as db:
        _ensure_watchlist_schema(db); item = db.get(WatchlistSubscription, subscription_id)
        if item is None: raise HTTPException(404, "Subscription not found")
        if payload.auto_record is not None: item.auto_record = payload.auto_record
        if payload.delay_seconds is not None: item.delay_seconds = payload.delay_seconds
        db.commit(); db.refresh(item); return _watchlist_data(item)

@app.delete("/watchlist/{subscription_id}", status_code=204)
def delete_watchlist(subscription_id: UUID):
    with SessionLocal() as db:
        _ensure_watchlist_schema(db); item = db.get(WatchlistSubscription, subscription_id)
        if item is None: raise HTTPException(404, "Subscription not found")
        eventsub_id = item.eventsub_subscription_id; db.delete(item); db.commit()
    if eventsub_id:
        try:
            from app.twitch_eventsub import delete_eventsub_subscription
            delete_eventsub_subscription(eventsub_id)
        except Exception:
            pass

@app.post("/webhooks/twitch/eventsub")
async def twitch_eventsub_webhook(request: Request):
    raw = await request.body()
    message_id = request.headers.get("twitch-eventsub-message-id", "")
    timestamp = request.headers.get("twitch-eventsub-message-timestamp", "")
    signature = request.headers.get("twitch-eventsub-message-signature", "")
    from app.twitch_eventsub import verify_eventsub_signature
    if not verify_eventsub_signature(message_id, timestamp, raw, signature):
        raise HTTPException(403, "Invalid EventSub signature")
    try: body = json.loads(raw)
    except json.JSONDecodeError as error: raise HTTPException(400, "Invalid JSON") from error
    message_type = request.headers.get("twitch-eventsub-message-type", "")
    if message_type == "webhook_callback_verification":
        return Response(content=str(body.get("challenge", "")), media_type="text/plain")
    # Twitch delivers at least once; Redis prevents duplicate scheduling.
    try:
        if not redis_client().set(f"twitch:eventsub:message:{message_id}", "1", nx=True, ex=86400):
            return Response(status_code=204)
    except Exception:
        pass
    if message_type == "notification" and body.get("subscription", {}).get("type") == "stream.online":
        from app.worker.watcher import handle_twitch_stream_online
        handle_twitch_stream_online.delay(body.get("event") or {})
    elif message_type == "revocation":
        revoked_id = body.get("subscription", {}).get("id")
        if revoked_id:
            with SessionLocal() as db:
                _ensure_watchlist_schema(db); item = db.query(WatchlistSubscription).filter(WatchlistSubscription.eventsub_subscription_id == revoked_id).first()
                if item: item.eventsub_subscription_id = None; db.commit()
    return Response(status_code=204)

@app.get("/notifications")
def list_notifications():
    with SessionLocal() as db:
        _ensure_watchlist_schema(db)
        items = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()
        return {"unread_count":db.query(Notification).filter(Notification.is_read.is_(False)).count(),"items":[_notification_data(item) for item in items]}

@app.post("/notifications/read-all", status_code=204)
def read_all_notifications():
    with SessionLocal() as db:
        _ensure_watchlist_schema(db); db.query(Notification).filter(Notification.is_read.is_(False)).update({"is_read":True}); db.commit()

@app.post("/notifications/{notification_id}/cancel")
def cancel_notification(notification_id: UUID):
    with SessionLocal() as db:
        _ensure_watchlist_schema(db); item = db.get(Notification, notification_id)
        if item is None: raise HTTPException(404, "Notification not found")
        if item.status != "pending_auto_record": raise HTTPException(409, "Auto-record is no longer pending")
        item.status = "cancelled"; item.is_read = True; db.commit(); db.refresh(item); return _notification_data(item)

@app.get("/streams")
def list_streams():
    with SessionLocal() as db:
        _ensure_preset_schema(db)
        streams = db.query(Stream).order_by(Stream.created_at.desc()).all()
        counts = dict(db.query(Clip.stream_id, func.count(Clip.id)).group_by(Clip.stream_id).all())
        return [{**stream_data(stream), "clip_count": counts.get(stream.id, 0)} for stream in streams]

@app.get("/archive/shorts")
def list_archive_shorts():
    """Flatten generated Shorts for the archive without making the dashboard poll each VOD."""
    with SessionLocal() as db:
        _ensure_preset_schema(db)
        rows = db.query(Clip, Stream).join(Stream, Clip.stream_id == Stream.id).order_by(Stream.created_at.desc(), Clip.viral_score.desc()).all()
        return [{
            "id": str(clip.id), "stream_id": str(stream.id), "source_url": stream.source_url,
            "platform": stream.platform, "remove_music": stream.remove_music,
            "start_seconds": clip.start_seconds, "end_seconds": clip.end_seconds,
            "transcript": clip.transcript, "transcript_snippet":clip.transcript_snippet or clip.transcript,"viral_score":clip.viral_score,"hook_title":clip.hook_title,"highlight_reason":clip.highlight_reason,"url": presigned_download_url(clip.vertical_key) if clip.vertical_key else None,
            "thumbnail_url": presigned_download_url(clip.thumbnail_key) if clip.thumbnail_key else None,
        } for clip, stream in rows]

@app.get("/streams/{stream_id}")
def stream_status(stream_id: UUID):
    with SessionLocal() as db:
        _ensure_preset_schema(db)
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        clips = db.query(Clip).filter(Clip.stream_id == stream_id).order_by(Clip.viral_score.desc(), Clip.start_seconds).all()
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
        if payload.remove_music is not None: stream.remove_music = payload.remove_music
        if payload.embed_intro_cover:
            branding = _branding(db)
            if branding.default_short_thumbnail_key:
                suffix = Path(branding.default_short_thumbnail_key).suffix or ".png"
                stream.short_thumbnail_key = f"streams/{stream.id}/short-thumbnail{suffix}"
                copy_file(branding.default_short_thumbnail_key, stream.short_thumbnail_key)
        db.commit()
    # Keep the Vercel API package lean; the Whisper worker imports this only in its own container.
    from app.worker.highlights import process_stream_highlights
    task = process_stream_highlights.delay(str(stream_id), payload.max_clips)
    redis_client().sadd(task_key(str(stream_id)), task.id); redis_client().expire(task_key(str(stream_id)), 43200)
    return {"id": str(stream_id), "status": StreamStatus.processing}

@app.post("/recordings/{stream_id}/clips/generate", status_code=202)
def generate_custom_clips(stream_id: UUID, payload: ProcessRequest):
    return process_stream(stream_id, payload)

# Public API alias retained for clients that use the Phase 8 naming.
@app.post("/streams/start", status_code=202)
def start_stream(payload: RecordRequest, request: Request):
    return record(payload, request)

@app.delete("/recordings/{stream_id}", status_code=204)
def delete_recording(stream_id: UUID):
    """Irreversible purge of task state, R2 media, local scratch and DB metadata."""
    sid = str(stream_id)
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: raise HTTPException(404, "Stream not found")
        clips = db.query(Clip).filter(Clip.stream_id == stream_id).all()
        keys = [key for key in [stream.master_key, stream.thumbnail_key, stream.short_thumbnail_key, stream.archive_logo_key] + [value for clip in clips for value in (clip.vertical_key, clip.thumbnail_key, clip.captions_key)] if key]
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
