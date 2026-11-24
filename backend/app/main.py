import base64
import os
import ipaddress
import hashlib
import hmac
import json
import secrets
import shutil
import time
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from html import unescape
from urllib.request import HTTPRedirectHandler, Request as UrlRequest, build_opener, urlopen
from urllib.parse import urlparse, urlunparse
from uuid import UUID, uuid4
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from botocore.exceptions import BotoCoreError, ClientError
from redis.exceptions import RedisError
from app.db import Base, SessionLocal, engine
from app.migrations import apply_migrations
from app.config import get_settings
from app.models import ArchiveBranding, Clip, CreatorSuggestion, Notification, SavedThumbnail, SessionCredential, SmartThumbnail, Stream, StreamStatus, StudioRender, Vod, VodStatus, WatchlistSubscription
from app.storage import StorageUnavailable, copy_file, delete_files, presigned_download_url, r2_client, upload_file
from app.worker.tasks import WORK_ROOT, active_key, redis_client, stop_key, task_key
from app.worker.celery_app import WORKER_HEARTBEAT_KEY, celery_app
from app.worker.vods import extract_vod_metadata
from app.worker.studio import render_studio
from app.api.credentials import router as credentials_router

app = FastAPI(title="Klipr.cloud API", description="On-demand creator stream capture and AI clip studio.", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in get_settings().klipr_cors_origins.split(",") if origin.strip()], allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"], allow_credentials=True)
app.include_router(credentials_router)

_schema_lock = threading.Lock()
_schema_initialized = False
_DATABASE_FREE_PATHS = {
    "/health", "/auth/password", "/auth/email", "/auth/me",
    "/auth/logout", "/streams/preview", "/docs", "/openapi.json",
}


class DatabaseUnavailable(RuntimeError):
    """Raised when a request needs the database but it is not configured."""


def _database_error_summary(error: Exception) -> str:
    """Keep production diagnostics useful without logging database credentials."""
    original = getattr(error, "orig", error)
    message = " ".join(str(original).split())
    message = re.sub(
        r"(postgres(?:ql)?(?:\+[^:]*)?://)[^@\s]+@",
        r"\1***@",
        message,
        flags=re.IGNORECASE,
    )
    return f"{type(error).__name__}: {message[:600]}"


def ensure_database_schema() -> None:
    """Initialize schema once per process, including serverless cold starts.

    Vercel/ASGI adapters do not consistently execute lifespan startup hooks.
    The PostgreSQL advisory transaction lock also makes concurrent cold starts
    safe: only one instance creates or migrates the schema at a time.
    """
    global _schema_initialized
    if _schema_initialized:
        return
    if engine is None:
        raise DatabaseUnavailable("DATABASE_URL is not configured")
    with _schema_lock:
        if _schema_initialized:
            return
        with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(1263357018)"))
            Base.metadata.create_all(bind=connection)
            apply_migrations(connection)
        _schema_initialized = True


@app.on_event("startup")
def initialize_database() -> None:
    """Eager initialization for conventional ASGI hosts."""
    if engine is None:
        return
    try:
        ensure_database_schema()
    except SQLAlchemyError as error:
        # Keep health/auth available while a transient database outage recovers.
        # The first later data request retries initialization.
        print(f"database startup initialization failed: {_database_error_summary(error)}")


@app.exception_handler(DatabaseUnavailable)
async def database_configuration_error(_request: Request, error: DatabaseUnavailable):
    return JSONResponse(
        status_code=503,
        content={"detail": "قاعدة البيانات غير مهيأة للخادم.", "code": "database_not_configured"},
    )


@app.exception_handler(SQLAlchemyError)
async def database_runtime_error(_request: Request, error: SQLAlchemyError):
    # Log the server-side exception without exposing credentials or SQL to users.
    print(f"database request failed: {_database_error_summary(error)}")
    return JSONResponse(
        status_code=503,
        content={"detail": "تعذّر الاتصال بقاعدة البيانات مؤقتًا. حاول مجددًا.", "code": "database_unavailable"},
    )


@app.exception_handler(RedisError)
async def redis_runtime_error(_request: Request, error: RedisError):
    print(f"redis request failed: {type(error).__name__}")
    return JSONResponse(
        status_code=503,
        content={"detail": "خدمة المهام غير متاحة مؤقتًا. حاول مجددًا.", "code": "queue_unavailable"},
    )


@app.exception_handler(StorageUnavailable)
async def storage_configuration_error(_request: Request, error: StorageUnavailable):
    return JSONResponse(
        status_code=503,
        content={"detail": "تخزين الوسائط غير مهيأ للخادم.", "code": "storage_not_configured"},
    )


@app.exception_handler(BotoCoreError)
@app.exception_handler(ClientError)
async def storage_runtime_error(_request: Request, error: Exception):
    print(f"storage request failed: {type(error).__name__}")
    return JSONResponse(
        status_code=503,
        content={"detail": "خدمة تخزين الوسائط غير متاحة مؤقتًا.", "code": "storage_unavailable"},
    )


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
    public_paths = {"/health", "/health/ready", "/auth/password", "/auth/email", "/auth/me", "/webhooks/twitch/eventsub", "/docs", "/openapi.json"}
    path = request.url.path.removeprefix("/api") or "/"
    public_suggestion = path == "/creator-suggestions" and request.method == "POST"
    if request.method == "OPTIONS" or path in public_paths or public_suggestion or _read_token(request.cookies.get("klipr_session"), "session"):
        if request.method != "OPTIONS" and path not in _DATABASE_FREE_PATHS:
            try:
                ensure_database_schema()
            except DatabaseUnavailable:
                return JSONResponse(status_code=503, content={"detail": "قاعدة البيانات غير مهيأة للخادم.", "code": "database_not_configured"})
            except SQLAlchemyError as error:
                print(f"database schema initialization failed: {type(error).__name__}")
                return JSONResponse(status_code=503, content={"detail": "تعذّر الاتصال بقاعدة البيانات مؤقتًا. حاول مجددًا.", "code": "database_unavailable"})
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
    overlay_creator_name: str | None = Field(default=None, max_length=120)
    overlay_position: str = "top-right"
    auto_merge_branding: bool = True
    ai_music_removal: bool = False

    @field_validator("overlay_position")
    @classmethod
    def valid_overlay_position(cls, value: str) -> str:
        if value not in {"top-right", "top-left", "bottom-center"}:
            raise ValueError("overlay_position must be top-right, top-left, or bottom-center")
        return value
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
class VodImportRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2000)
    quality: str = "4k"


class AiMetadataRequest(BaseModel):
    vod_id: UUID
    regenerate: bool = False


class SmartThumbnailRequest(BaseModel):
    vod_id: UUID
    platform: str = "youtube"
    frame_style: str = "bold"

    @field_validator("platform")
    @classmethod
    def validate_thumbnail_platform(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"youtube", "tiktok", "shorts", "reels", "x", "kick"}:
            raise ValueError("Unsupported thumbnail platform")
        return value

    @field_validator("frame_style")
    @classmethod
    def validate_frame_style(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"bold", "clean", "none"}:
            raise ValueError("Unsupported frame style")
        return value


def studio_render_data(item: StudioRender) -> dict:
    return {"id": str(item.id), "vod_id": str(item.vod_id), "status": item.status,
            "progress": item.progress, "export_quality": item.export_quality, "start_seconds": item.start_seconds, "end_seconds": item.end_seconds, "error": item.error_message,
            "download_url": f"/studio/renders/{item.id}/download" if item.status == "ready" and item.output_path else None,
            "created_at": item.created_at.isoformat() if item.created_at else None}


def smart_thumbnail_data(item: SmartThumbnail) -> dict:
    return {"id": str(item.id), "vod_id": str(item.vod_id), "status": item.status,
            "progress": round(item.progress or 0, 1), "platform": item.platform,
            "frame_style": item.frame_style, "timestamp_seconds": item.timestamp_seconds,
            "headline": item.headline, "context": item.context, "error": item.error_message,
            "image_url": f"/smart-thumbnails/{item.id}/image" if item.status == "ready" and item.output_path else None,
            "created_at": item.created_at.isoformat() if item.created_at else None}


async def _save_studio_upload(file: UploadFile | None, destination: Path, allowed: set[str], maximum: int) -> str | None:
    if file is None or not file.filename:
        return None
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(422, f"Unsupported file type: {suffix or 'unknown'}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > maximum:
                output.close(); destination.unlink(missing_ok=True)
                raise HTTPException(413, "The uploaded file is too large")
            output.write(chunk)
    return str(destination)

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


def normalize_vod_url(value: str) -> tuple[str, str]:
    """Accept public archive URLs from any yt-dlp supported video platform."""
    parsed = urlparse(value.strip())
    try:
        port = parsed.port
    except ValueError as error:
        raise HTTPException(422, "Invalid port") from error
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in {None, 443}:
        raise HTTPException(422, "A standard HTTPS VOD URL is required")
    try:
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise HTTPException(422, "Invalid hostname") from error
    path = parsed.path.rstrip("/")
    if not host or host == "localhost" or host.endswith(".localhost") or not path:
        raise HTTPException(422, "A public HTTPS video URL is required")
    try:
        if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback:
            raise HTTPException(422, "Private network addresses are not allowed")
    except ValueError:
        pass
    platform = "twitch" if host in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"} else "kick" if host in {"kick.com", "www.kick.com"} else "web"
    return platform, urlunparse(("https", host, path, "", parsed.query, ""))


def vod_data(vod: Vod) -> dict:
    return {
        "id": str(vod.id), "url": vod.source_url, "platform": vod.platform, "quality": vod.quality,
        "status": vod.status.value if isinstance(vod.status, VodStatus) else vod.status,
        "title": vod.title, "streamer_name": vod.streamer_name, "duration_seconds": vod.duration_seconds,
        "thumbnail_url": f"/vods/{vod.id}/thumbnail" if vod.thumbnail_key else vod.thumbnail_url,
        "progress": round(vod.progress or 0, 1), "download_speed": vod.download_speed,
        "eta_seconds": vod.eta_seconds, "file_size": vod.file_size, "width": vod.width,
        "height": vod.height, "fps": vod.fps, "bitrate": vod.bitrate, "error": vod.error_message,
        "download_url": f"/vods/{vod.id}/download" if vod.status == VodStatus.ready else None,
        "created_at": vod.created_at, "updated_at": vod.updated_at,
    }


def _vod_is_stale(vod: Vod) -> bool:
    active = {VodStatus.fetching_metadata, VodStatus.downloading, VodStatus.remuxing}
    if vod.status not in active or not vod.updated_at:
        return False
    updated = vod.updated_at if vod.updated_at.tzinfo else vod.updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated > timedelta(minutes=20)


def _expire_stale_vod(db, vod: Vod) -> None:
    if not _vod_is_stale(vod):
        return
    vod.status = VodStatus.failed
    vod.error_message = "توقفت مهمة الاستخراج لأن عامل المعالجة لم يكن متصلاً. أعد المحاولة الآن."
    vod.download_speed = None
    vod.eta_seconds = None
    db.commit()


def _vod_task_key(vod_id: UUID) -> str:
    return f"klipr:vod:task:{vod_id}"


def _vod_lock_key(vod_id: UUID) -> str:
    return f"klipr:vod:lock:{vod_id}"


def _find_vod_task(vod_id: UUID) -> str | None:
    """Return the queued/running Celery task id, including legacy jobs."""
    try:
        value = redis_client().get(_vod_task_key(vod_id))
        if value:
            return value.decode() if isinstance(value, bytes) else str(value)
    except RedisError:
        pass
    try:
        inspector = celery_app.control.inspect(timeout=2)
        groups = (inspector.active() or {}, inspector.reserved() or {}, inspector.scheduled() or {})
        for group in groups:
            for tasks in group.values():
                for task in tasks:
                    request = task.get("request", task)
                    args = request.get("args") or task.get("args") or []
                    if str(vod_id) in str(args):
                        return str(request.get("id") or task.get("id"))
    except Exception:
        pass
    return None


def _cancel_vod_task(vod_id: UUID) -> bool:
    task_id = _find_vod_task(vod_id)
    if task_id:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    try:
        redis_client().delete(_vod_task_key(vod_id), _vod_lock_key(vod_id))
    except RedisError:
        pass
    return bool(task_id)

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


@app.get("/health/ready")
def readiness():
    """Verify the dependencies required by dashboard and background jobs."""
    ensure_database_schema()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    queue_ok = False
    worker_ok = False
    try:
        client = redis_client()
        queue_ok = bool(client.ping())
        worker_ok = bool(client.exists(WORKER_HEARTBEAT_KEY))
    except RedisError:
        pass
    storage_ok = False
    try:
        r2_client().head_bucket(Bucket=get_settings().r2_bucket)
        storage_ok = True
    except (StorageUnavailable, BotoCoreError, ClientError):
        pass
    ready = queue_ok and storage_ok and worker_ok
    payload = {
        "ok": ready,
        "database": "ready",
        "queue": "ready" if queue_ok else "unavailable",
        "worker": "ready" if worker_ok else "unavailable",
        "storage": "ready" if storage_ok else "unavailable",
    }
    return payload if ready else JSONResponse(status_code=503, content=payload)


@app.post("/vods/import", status_code=202)
def create_vod_import(payload: VodImportRequest):
    platform, normalized_url = normalize_vod_url(payload.url)
    # Imports use one deliberate mastering profile: 4K at 60fps.
    quality = payload.quality.strip().lower() or "4k"
    if quality != "4k":
        raise HTTPException(422, "quality must be 4k")
    try:
        info = extract_vod_metadata(normalized_url)
    except Exception as error:
        raise HTTPException(502, "تعذّر استخراج بيانات البث. تأكد أن الرابط عام ومتاح.") from error
    title = str(info.get("title") or "Untitled VOD")[:500]
    uploader = str(info.get("uploader") or info.get("channel") or info.get("uploader_id") or "")[:160]
    duration = int(info["duration"]) if info.get("duration") else None
    thumbnail_url = info.get("thumbnail")
    if info.get("availability") == "subscriber_only":
        with SessionLocal() as db:
            credential = db.get(SessionCredential, platform)
            has_session = bool(credential and credential.status == "active" and credential.session_encrypted)
            if has_session and credential.expires_at:
                expires_at = credential.expires_at if credential.expires_at.tzinfo else credential.expires_at.replace(tzinfo=timezone.utc)
                has_session = expires_at > datetime.now(timezone.utc)
        if not has_session:
            raise HTTPException(403, "هذا البث مخصص لمشتركي Kick. أضف جلسة Kick صالحة من قسم الجلسة ثم أعد المحاولة.")
    try:
        worker_online = bool(redis_client().exists(WORKER_HEARTBEAT_KEY))
    except RedisError:
        worker_online = False
    if not worker_online:
        raise HTTPException(503, "عامل الاستخراج غير متصل حالياً. لم يتم إنشاء مهمة معلّقة.")
    with SessionLocal() as db:
        existing = db.query(Vod).filter(Vod.source_url == normalized_url).first()
        if existing and existing.status == VodStatus.ready and existing.quality == quality:
            return vod_data(existing)
        if existing and existing.status in {VodStatus.fetching_metadata, VodStatus.downloading, VodStatus.remuxing} and not _vod_is_stale(existing):
            return vod_data(existing)
        vod = existing or Vod(source_url=normalized_url, platform=platform)
        vod.quality = quality
        vod.status = VodStatus.downloading
        vod.title = title
        vod.streamer_name = uploader
        vod.duration_seconds = duration
        vod.thumbnail_url = thumbnail_url
        vod.progress = 1
        vod.error_message = None
        vod.download_speed = None
        vod.eta_seconds = None
        if existing is None: db.add(vod)
        db.commit(); db.refresh(vod)
        response = vod_data(vod)
    try:
        task = celery_app.send_task("app.worker.vods.import_vod", args=[str(vod.id)])
        try:
            redis_client().set(_vod_task_key(vod.id), task.id, ex=86400)
        except RedisError:
            pass
    except Exception as error:
        with SessionLocal() as db:
            failed = db.get(Vod, vod.id)
            if failed:
                failed.status = VodStatus.failed
                failed.error_message = "تعذّر إرسال مهمة الاستخراج إلى الطابور."
                db.commit()
        raise HTTPException(503, "تعذّر بدء الاستخراج حالياً.") from error
    return response


@app.get("/vods")
def list_vods():
    with SessionLocal() as db:
        items = db.query(Vod).order_by(Vod.created_at.desc()).all()
        for item in items: _expire_stale_vod(db, item)
        return [vod_data(item) for item in items]


@app.get("/vods/status/{job_id}")
def vod_status(job_id: UUID):
    with SessionLocal() as db:
        item = db.get(Vod, job_id)
        if item is None: raise HTTPException(404, "VOD job not found")
        _expire_stale_vod(db, item)
        return vod_data(item)


def _chapter_time(seconds: float) -> str:
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


@app.post("/ai-metadata/generate")
def generate_ai_metadata(payload: AiMetadataRequest):
    """Generate publish-ready Arabic metadata from available clip transcripts."""
    with SessionLocal() as db:
        vod = db.get(Vod, payload.vod_id)
        if vod is None: raise HTTPException(404, "VOD not found")
        if vod.status != VodStatus.ready: raise HTTPException(409, "Select a ready VOD first")
        streams = db.query(Stream).filter(Stream.source_url == vod.source_url).all()
        clips = db.query(Clip).filter(Clip.stream_id.in_([item.id for item in streams])).order_by(Clip.viral_score.desc(), Clip.score.desc()).all() if streams else []
        # Metadata must describe what actually occurred in the VOD. A source
        # title is context only; it is never sufficient evidence for a title,
        # description, or chapter.
        evidence = [{
            "time": _chapter_time(clip.start_seconds),
            "end_time": _chapter_time(clip.end_seconds),
            "viral_score": clip.viral_score or 0,
            "event": clip.hook_title or clip.highlight_reason or "",
            "reason": clip.highlight_reason or "",
            "spoken_words": (clip.transcript_snippet or clip.transcript or "").strip(),
        } for clip in clips]
        evidence = [event for event in evidence if event["event"] or event["spoken_words"]]
        if not evidence:
            raise HTTPException(409, "حلّل أحداث البث أولاً. لا يمكن إنشاء عنوان أو وصف احترافي من عنوان البث فقط.")
        transcript = " ".join(event["spoken_words"] for event in evidence).strip()[:12000]
        moments = [{"time": event["time"], "title": event["event"] or event["spoken_words"][:80]} for event in sorted(evidence, key=lambda event: event["time"])[:12]]
        title = (vod.title or "بث مباشر").strip()
        creator = (vod.streamer_name or "صانع المحتوى").strip()
        duration = int(vod.duration_seconds or 0)

    strongest_events = [event["event"] or event["spoken_words"][:70] for event in evidence[:3]]
    lead_event = strongest_events[0]
    base_titles = [
        f"{lead_event} | أقوى لحظات {creator}",
        f"{lead_event}... ردة الفعل كانت غير متوقعة! 🔥",
        f"{strongest_events[1] if len(strongest_events) > 1 else lead_event} | من أقوى أحداث البث",
        f"أبرز ما حدث في البث: {lead_event}",
        f"{lead_event} و{strongest_events[1] if len(strongest_events) > 1 else 'لحظات لا تُفوّت'}",
    ]
    chapters = moments
    fallback = {
        "titles": [{"text": value, "score": score} for value, score in zip(base_titles, (94, 91, 89, 87, 85))],
        "description": f"في هذا البث من {creator}: {lead_event}. كما شهدنا {strongest_events[1] if len(strongest_events) > 1 else 'لحظات بارزة أخرى'} — وهذه أبرز الأحداث مرتبة حسب قوتها.\n\nاشتركوا وفعّلوا التنبيهات لمتابعة المقاطع الجديدة.",
        "chapters": chapters,
        "tags": [creator, "بث مباشر", "قيمز", "مقاطع", "أفضل اللحظات", "Klipr"],
        "hashtags": ["#بث_مباشر", "#قيمز", "#مقاطع", "#Klipr"],
        "source": "vod-events",
    }
    settings = get_settings()
    if not settings.deepseek_api_key:
        return fallback
    prompt = f"""أنت محرر يوتيوب عربي محترف. أعد JSON فقط بالمفاتيح: titles (خمسة عناصر text وscore من 100)، description، chapters (time وtitle)، tags، hashtags. اجعل العناوين جذابة بلا تضليل والوصف متوافقاً مع SEO. قاعدة إلزامية: ابنِ كل ادعاء على أحداث البث المثبتة أدناه، ولا تستخدم عنوان البث إلا كسياق ثانوي ولا تخترع أحداثاً. اسم القناة: {creator}. عنوان البث (سياق فقط): {title}. المدة: {duration} ثانية. أدلة الأحداث مرتبة بالقوة: {json.dumps(evidence[:12], ensure_ascii=False)}. التفريغ: {transcript}. صياغة مختلفة: {payload.regenerate}."""
    try:
        request = UrlRequest(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps({"model":"deepseek-chat","messages":[{"role":"user","content":prompt}],"temperature":.9 if payload.regenerate else .65,"response_format":{"type":"json_object"}}, ensure_ascii=False).encode(),
            headers={"Authorization":f"Bearer {settings.deepseek_api_key}","Content-Type":"application/json","User-Agent":"Klipr.cloud/1.0"},
            method="POST",
        )
        with urlopen(request, timeout=45) as response:
            content = json.loads(response.read(2_000_000))["choices"][0]["message"]["content"]
        generated = json.loads(content)
        if not isinstance(generated.get("titles"), list) or not generated["titles"]:
            raise ValueError("AI response did not include titles")
        for key in ("description", "chapters", "tags", "hashtags"):
            if key not in generated:
                raise ValueError(f"AI response did not include {key}")
        generated["source"] = "ai-vod-events"
        return generated
    except Exception:
        return fallback


@app.post("/vods/{vod_id}/cancel")
def cancel_vod(vod_id: UUID):
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None: raise HTTPException(404, "VOD not found")
        if item.status == VodStatus.ready: raise HTTPException(409, "The VOD is already ready")
        _cancel_vod_task(vod_id)
        item.status = VodStatus.failed
        item.error_message = "تم إلغاء المعالجة فورياً بواسطة المستخدم."
        item.download_speed = None
        item.eta_seconds = None
        db.commit(); db.refresh(item)
        response = vod_data(item)
    time.sleep(0.4)
    shutil.rmtree(Path("/var/lib/klipr/vods") / str(vod_id), ignore_errors=True)
    return response


@app.get("/vods/{vod_id}/download")
def download_vod(vod_id: UUID):
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None: raise HTTPException(404, "VOD not found")
        if not item.storage_key: raise HTTPException(404, "VOD file is not available")
        return RedirectResponse(presigned_download_url(item.storage_key), status_code=307)


@app.get("/vods/{vod_id}/thumbnail")
def vod_thumbnail(vod_id: UUID):
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None: raise HTTPException(404, "VOD not found")
        if not item.thumbnail_key: raise HTTPException(404, "VOD thumbnail is not available")
        return RedirectResponse(presigned_download_url(item.thumbnail_key), status_code=307)


@app.post("/vods/{vod_id}/open-in-editor", status_code=201)
def open_vod_in_editor(vod_id: UUID):
    """Stage the original VOD for the existing clip worker, only when the user opens it."""
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None: raise HTTPException(404, "VOD not found")
        if not item.storage_key: raise HTTPException(409, "VOD file is not ready")
        branding = _branding(db)
        stream = Stream(source_url=item.source_url, platform=item.platform, status=StreamStatus.ready,
                        started_at=item.created_at, ended_at=item.updated_at, remove_music=branding.remove_music,
                        enable_end_screen=branding.enable_end_screen, archive_channel_name=branding.archive_channel_name,
                        archive_tagline=branding.archive_tagline, outro_duration_seconds=branding.outro_duration_seconds,
                        overlay_creator_name=branding.overlay_creator_name, overlay_position=branding.overlay_position)
        db.add(stream); db.flush()
        key = f"streams/{stream.id}/master.mp4"
        copy_file(item.storage_key, key)
        stream.master_key = key
        if item.thumbnail_key:
            thumb_key = f"streams/{stream.id}/thumbnail.jpg"
            copy_file(item.thumbnail_key, thumb_key)
            stream.thumbnail_key = thumb_key
        if branding.overlay_logo_key:
            suffix = Path(branding.overlay_logo_key).suffix or ".png"
            stream.overlay_logo_key = f"streams/{stream.id}/overlay-logo{suffix}"
            copy_file(branding.overlay_logo_key, stream.overlay_logo_key)
        if branding.default_short_thumbnail_key:
            suffix = Path(branding.default_short_thumbnail_key).suffix or ".png"
            stream.short_thumbnail_key = f"streams/{stream.id}/short-thumbnail{suffix}"
            copy_file(branding.default_short_thumbnail_key, stream.short_thumbnail_key)
        db.commit(); db.refresh(stream)
        return stream_data(stream)


@app.post("/vods/{vod_id}/generate-clips", status_code=202)
def generate_vod_clips(vod_id: UUID, payload: ProcessRequest = ProcessRequest()):
    """The VOD Vault one-click route: stage, brand and queue clips in one request."""
    stream = open_vod_in_editor(vod_id)
    return process_stream(UUID(stream["id"]), payload)


@app.delete("/vods/{vod_id}", status_code=204)
def delete_vod(vod_id: UUID):
    _cancel_vod_task(vod_id)
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None: raise HTTPException(404, "VOD not found")
        storage_keys = [key for key in (item.storage_key, item.thumbnail_key) if key]
        db.delete(item); db.commit()
    delete_files(storage_keys)
    time.sleep(0.2)
    shutil.rmtree(Path("/var/lib/klipr/vods") / str(vod_id), ignore_errors=True)


@app.post("/studio/renders", status_code=202)
async def create_studio_render(
    vod_id: UUID = Form(...),
    export_quality: str = Form("original"),
    start_seconds: float | None = Form(None),
    end_seconds: float | None = Form(None),
    intro: UploadFile | None = File(None),
    outro: UploadFile | None = File(None),
):
    """Persist local assets then dispatch an isolated FFmpeg normalization job."""
    with SessionLocal() as db:
        vod = db.get(Vod, vod_id)
        if vod is None or vod.status != VodStatus.ready or not vod.storage_key:
            raise HTTPException(409, "Select a ready VOD from the vault first")
        if export_quality not in {"original", "4k"}:
            raise HTTPException(422, "export_quality must be original or 4k")
        if start_seconds is not None and start_seconds < 0: raise HTTPException(422, "start_seconds must be positive")
        if end_seconds is not None and (start_seconds is None or end_seconds <= start_seconds): raise HTTPException(422, "end_seconds must be after start_seconds")
        if end_seconds is not None and vod.duration_seconds and end_seconds > vod.duration_seconds: raise HTTPException(422, "end_seconds exceeds the VOD duration")
        render = StudioRender(vod_id=vod_id, status="queued", progress=0, export_quality=export_quality, start_seconds=start_seconds, end_seconds=end_seconds)
        db.add(render); db.commit(); db.refresh(render)
        render_id = render.id
    folder = Path("/var/lib/klipr/studio") / str(render_id)
    try:
        intro_path = await _save_studio_upload(intro, folder / "intro.mp4", {".mp4", ".mov"}, 20 * 1024 * 1024 * 1024)
        outro_path = await _save_studio_upload(outro, folder / "outro.mp4", {".mp4", ".mov"}, 20 * 1024 * 1024 * 1024)
        # API runs as root to accept uploads; the Celery media worker is
        # intentionally unprivileged. Hand this job directory to that worker.
        os.chown(folder, 10001, 10001)
        for uploaded in (intro_path, outro_path):
            if uploaded:
                os.chown(uploaded, 10001, 10001)
        with SessionLocal() as db:
            item = db.get(StudioRender, render_id)
            item.intro_path, item.outro_path = intro_path, outro_path
            db.commit(); db.refresh(item)
            response = studio_render_data(item)
        render_studio.delay(str(render_id))
        return response
    except HTTPException:
        with SessionLocal() as db:
            item = db.get(StudioRender, render_id)
            if item: db.delete(item); db.commit()
        raise
    except Exception as error:
        with SessionLocal() as db:
            item = db.get(StudioRender, render_id)
            if item: item.status = "failed"; item.error_message = str(error)[:1000]; db.commit()
        raise HTTPException(500, "Unable to save studio assets") from error


@app.get("/studio/renders/{render_id}")
def studio_render_status(render_id: UUID):
    with SessionLocal() as db:
        item = db.get(StudioRender, render_id)
        if item is None: raise HTTPException(404, "Studio render not found")
        return studio_render_data(item)


@app.get("/studio/renders/{render_id}/download")
def download_studio_render(render_id: UUID):
    with SessionLocal() as db:
        item = db.get(StudioRender, render_id)
        if item is None or item.status != "ready" or not item.output_path:
            raise HTTPException(404, "The final render is not ready")
        output = Path(item.output_path)
    if not output.is_file(): raise HTTPException(404, "The final render file is unavailable")
    return FileResponse(output, media_type="video/mp4", filename=f"klipr-studio-{render_id}.mp4")


@app.post("/smart-thumbnails", status_code=202)
def create_smart_thumbnails(payload: SmartThumbnailRequest):
    """Queue three AI-assisted thumbnail candidates for a ready VOD."""
    with SessionLocal() as db:
        vod = db.get(Vod, payload.vod_id)
        if vod is None or vod.status != VodStatus.ready or not vod.storage_key:
            raise HTTPException(409, "Select a ready VOD from the vault first")
        streams = db.query(Stream).filter(Stream.source_url == vod.source_url).all()
        has_events = bool(streams) and db.query(Clip.id).filter(Clip.stream_id.in_([stream.id for stream in streams])).first() is not None
        if not has_events:
            raise HTTPException(409, "حلّل أحداث البث أولاً. صانع الثامبنيل يختار من أبرز الأحداث، وليس من لقطات عشوائية.")
        items = [SmartThumbnail(vod_id=vod.id, platform=payload.platform, frame_style=payload.frame_style) for _ in range(3)]
        db.add_all(items); db.commit()
        for item in items: db.refresh(item)
        response = [smart_thumbnail_data(item) for item in items]
    celery_app.send_task("app.worker.smart_thumbnails.generate_smart_thumbnails", args=[[item["id"] for item in response]])
    return response


@app.get("/smart-thumbnails/{thumbnail_id}")
def smart_thumbnail_status(thumbnail_id: UUID):
    with SessionLocal() as db:
        item = db.get(SmartThumbnail, thumbnail_id)
        if item is None: raise HTTPException(404, "Thumbnail not found")
        return smart_thumbnail_data(item)


@app.get("/smart-thumbnails/{thumbnail_id}/image")
def download_smart_thumbnail(thumbnail_id: UUID):
    with SessionLocal() as db:
        item = db.get(SmartThumbnail, thumbnail_id)
        if item is None or item.status != "ready" or not item.output_path:
            raise HTTPException(404, "Thumbnail is not ready")
        output = Path(item.output_path)
    if not output.is_file(): raise HTTPException(404, "Thumbnail file is unavailable")
    return FileResponse(output, media_type="image/jpeg", filename=f"klipr-thumbnail-{thumbnail_id}.jpg")


@app.post("/smart-thumbnails/{thumbnail_id}/approve")
def approve_smart_thumbnail(thumbnail_id: UUID):
    """Save an approved AI candidate into the persistent thumbnail library."""
    with SessionLocal() as db:
        candidate = db.get(SmartThumbnail, thumbnail_id)
        if candidate is None or candidate.status != "ready" or not candidate.output_path:
            raise HTTPException(409, "Thumbnail is not ready for approval")
        output = Path(candidate.output_path)
        if not output.is_file():
            raise HTTPException(404, "Thumbnail output is unavailable")
        key = f"branding/thumbnails/ai-{thumbnail_id}.jpg"
        upload_file(output, key, "image/jpeg")
        branding = _branding(db)
        branding.default_thumbnail_key = key
        branding.use_default_thumbnail = True
        saved = SavedThumbnail(kind="vod", storage_key=key)
        db.add(saved); db.commit(); db.refresh(saved)
        return {"id": str(saved.id), "kind": "vod", "key": key, "url": presigned_download_url(key), "selected": True}

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
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS overlay_logo_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS overlay_creator_name VARCHAR(120)"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS overlay_position VARCHAR(24) NOT NULL DEFAULT 'top-right'"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS auto_merge_branding BOOLEAN NOT NULL DEFAULT TRUE"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_intro_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_outro_key TEXT"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS ai_music_removal BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS channel_banner_key TEXT"))
        db.execute(text("ALTER TABLE streams ADD COLUMN IF NOT EXISTS overlay_logo_key TEXT"))
        db.execute(text("ALTER TABLE streams ADD COLUMN IF NOT EXISTS overlay_creator_name VARCHAR(120)"))
        db.execute(text("ALTER TABLE streams ADD COLUMN IF NOT EXISTS overlay_position VARCHAR(24) NOT NULL DEFAULT 'top-right'"))
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
        item = _branding(db); return {"enable_end_screen":item.enable_end_screen,"remove_music":item.remove_music,"auto_trim_ads":item.auto_trim_ads,"use_default_thumbnail":item.use_default_thumbnail,"outro_duration_seconds":item.outro_duration_seconds,"archive_channel_name":item.archive_channel_name,"archive_tagline":item.archive_tagline,"archive_logo_key":item.archive_logo_key,"archive_logo_url":presigned_download_url(item.archive_logo_key) if item.archive_logo_key else None,"default_thumbnail_key":item.default_thumbnail_key,"default_thumbnail_url":presigned_download_url(item.default_thumbnail_key) if item.default_thumbnail_key else None,"default_short_thumbnail_key":item.default_short_thumbnail_key,"default_short_thumbnail_url":presigned_download_url(item.default_short_thumbnail_key) if item.default_short_thumbnail_key else None,"default_left_vod_id":item.default_left_vod_id,"default_right_vod_id":item.default_right_vod_id,"overlay_logo_key":item.overlay_logo_key,"overlay_logo_url":presigned_download_url(item.overlay_logo_key) if item.overlay_logo_key else None,"overlay_creator_name":item.overlay_creator_name,"overlay_position":item.overlay_position,"auto_merge_branding":item.auto_merge_branding,"default_intro_key":item.default_intro_key,"default_outro_key":item.default_outro_key,"ai_music_removal":item.ai_music_removal,"channel_banner_key":item.channel_banner_key,"channel_banner_url":presigned_download_url(item.channel_banner_key) if item.channel_banner_key else None}
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

@app.post("/branding/overlay-logo")
async def upload_overlay_logo(file: UploadFile = File(...)):
    """Upload the transparent logo used by the editing-preset overlay."""
    data = await file.read()
    is_png, is_jpg, is_webp = data.startswith(b"\x89PNG\r\n\x1a\n"), data.startswith(b"\xff\xd8\xff"), data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if len(data) > 5 * 1024 * 1024 or not (is_png or is_jpg or is_webp):
        raise HTTPException(422, "Overlay logo must be a PNG, JPG, or WebP under 5MB")
    import tempfile
    suffix = ".png" if is_png else ".jpg" if is_jpg else ".webp"
    key = f"branding/overlay-logo_{secrets.token_hex(12)}{suffix}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
        temp.write(data); path = Path(temp.name)
    try:
        upload_file(path, key, "image/png" if suffix == ".png" else "image/jpeg")
        with SessionLocal() as db:
            item = _branding(db); old = item.overlay_logo_key; item.overlay_logo_key = key; db.commit()
        if old: delete_files([old])
    finally:
        path.unlink(missing_ok=True)
    return {"overlay_logo_key": key, "overlay_logo_url": presigned_download_url(key)}

@app.delete("/branding/overlay-logo", status_code=204)
def delete_overlay_logo():
    with SessionLocal() as db:
        item = _branding(db); old = item.overlay_logo_key; item.overlay_logo_key = None; db.commit()
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
            use_default_thumbnail = bool(item.use_default_thumbnail)
            db.commit()
    finally: path.unlink(missing_ok=True)
    return {"kind":kind,"key":key,"url":presigned_download_url(key),"use_default_thumbnail":use_default_thumbnail}

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


@app.get("/branding/thumbnails/{thumbnail_id}/download")
def download_saved_thumbnail(thumbnail_id: UUID):
    """Stream a saved cover through Klipr so browser CORS never blocks download."""
    with SessionLocal() as db:
        item = db.get(SavedThumbnail, thumbnail_id)
        if item is None:
            raise HTTPException(404, "Saved thumbnail not found")
        key = item.storage_key
    suffix = Path(key).suffix.lower()
    content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "application/octet-stream")
    try:
        body = r2_client().get_object(Bucket=get_settings().r2_bucket, Key=key)["Body"]
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(502, "Thumbnail storage is temporarily unavailable") from error
    return StreamingResponse(
        body.iter_chunks(chunk_size=1024 * 1024),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="klipr-{item.kind}-thumbnail{suffix}"'},
    )

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
            stream = Stream(channel_id=None, source_url=normalized, platform=platform, status=StreamStatus.queued, layout_mode=layout_mode, discord_webhook_url=webhook, custom_headline=(payload.custom_headline or "").strip()[:160] or None, enable_end_screen=branding.enable_end_screen, remove_music=branding.remove_music if payload.remove_music is None else payload.remove_music, archive_channel_name=branding.archive_channel_name, archive_tagline=branding.archive_tagline, outro_duration_seconds=branding.outro_duration_seconds, left_vod_id=branding.default_left_vod_id, right_vod_id=branding.default_right_vod_id, overlay_creator_name=branding.overlay_creator_name, overlay_position=branding.overlay_position)
            db.add(stream); db.flush()
            if branding.default_thumbnail_key and branding.use_default_thumbnail:
                suffix = Path(branding.default_thumbnail_key).suffix or ".png"
                stream.thumbnail_key = f"streams/{stream.id}/custom-thumbnail{suffix}"
                copy_file(branding.default_thumbnail_key, stream.thumbnail_key)
            if branding.archive_logo_key:
                suffix = Path(branding.archive_logo_key).suffix or ".png"
                stream.archive_logo_key = f"streams/{stream.id}/archive-logo{suffix}"
                copy_file(branding.archive_logo_key, stream.archive_logo_key)
            if branding.overlay_logo_key:
                suffix = Path(branding.overlay_logo_key).suffix or ".png"
                stream.overlay_logo_key = f"streams/{stream.id}/overlay-logo{suffix}"
                copy_file(branding.overlay_logo_key, stream.overlay_logo_key)
            if branding.default_short_thumbnail_key:
                suffix = Path(branding.default_short_thumbnail_key).suffix or ".png"
                stream.short_thumbnail_key = f"streams/{stream.id}/short-thumbnail{suffix}"
                copy_file(branding.default_short_thumbnail_key, stream.short_thumbnail_key)
            db.commit(); db.refresh(stream)
            if not _reserve_recording_slot(owner_key, str(stream.id)):
                db.delete(stream); db.commit()
                raise HTTPException(429, {"detail": "Maximum of two active recordings reached"})
        client.set(lock, str(stream.id), xx=True, ex=43200)
        task = celery_app.send_task("app.worker.tasks.record_stream", args=[str(stream.id), normalized, owner_key]); client.sadd(task_key(str(stream.id)), task.id); client.expire(task_key(str(stream.id)), 43200)
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
        celery_app.send_task("app.worker.watcher.handle_twitch_stream_online", args=[body.get("event") or {}])
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
        # Persist the queued state before dispatching Celery so every client
        # immediately sees that automatic editing has started.
        stream.status = StreamStatus.processing
        stream.error_message = None
        db.commit()
    # Keep the Vercel API package lean; the Whisper worker imports this only in its own container.
    task = celery_app.send_task("app.worker.highlights.process_stream_highlights", args=[str(stream_id), payload.max_clips])
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
            for task_id in redis_client().smembers(task_key(sid)): celery_app.control.revoke(task_id, terminate=True)
        finally:
            client = redis_client(); client.set(stop_key(sid), "1", ex=300); client.delete(active_key(source_url), task_key(sid))
        try: delete_files(keys)
        finally:
            import shutil
            shutil.rmtree(WORK_ROOT / sid, ignore_errors=True)
            db.delete(stream); db.commit()
