"""Direct URL recording tasks. No polling or scheduler is used."""
import subprocess
import time
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
import redis
from celery import shared_task
from app.config import get_settings
from app.db import SessionLocal
from app.core.crypto import decrypt_secret
from app.models import Notification, SessionCredential, Stream, StreamStatus
from app.storage import download_file, upload_file

WORK_ROOT = Path("/var/lib/klipr")

def redis_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)

def stop_key(stream_id: str) -> str: return f"stop_stream:{stream_id}"
def active_key(url: str) -> str: return f"active_stream:{url}"
def task_key(stream_id: str) -> str: return f"stream_tasks:{stream_id}"

def _release_owner(owner_key: str | None, stream_id: str) -> None:
    if owner_key:
        redis_client().srem(owner_key, stream_id)

def _set_status(stream_id: UUID, status: StreamStatus, **fields: object) -> None:
    with SessionLocal() as db:
        stream = db.get(Stream, stream_id)
        if stream is None: return
        stream.status = status
        for name, value in fields.items(): setattr(stream, name, value)
        db.commit()

def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill()


def _expire_session(platform: str) -> None:
    """Mark the vault entry expired and create one high-priority bell alert."""
    with SessionLocal() as db:
        credential = db.get(SessionCredential, platform)
        if not credential or credential.status == "expired": return
        credential.status = "expired"
        existing = db.query(Notification).filter(Notification.status == "session_expired", Notification.channel_url == f"session://{platform}", Notification.is_read.is_(False)).first()
        if not existing:
            label = "Kick" if platform == "kick" else "Twitch"
            db.add(Notification(title=f"انتهت صلاحية جلسة {label}", message=f"انتهت صلاحية جلسة {label} — يرجى تجديد الجلسة للاستمرار في التسجيل بجودة 1080p60", channel_url=f"session://{platform}", status="session_expired", is_read=False))
        db.commit()


def _session_capture_options(platform: str, scratch: Path) -> tuple[list[str], Path | None]:
    """Return Streamlink flags from an encrypted vault entry, never plaintext logs."""
    if platform not in {"kick", "twitch"}: return [], None
    with SessionLocal() as db:
        credential = db.get(SessionCredential, platform)
        if not credential or credential.status != "active" or not credential.session_encrypted:
            return (["--twitch-disable-ads"] if platform == "twitch" else []), None
        if credential.expires_at and credential.expires_at <= datetime.now(timezone.utc):
            _expire_session(platform)
            return (["--twitch-disable-ads"] if platform == "twitch" else []), None
        plaintext = decrypt_secret(credential.session_encrypted)
    cookie_file = scratch / f"{platform}_cookies.txt"
    cookie_file.write_text(plaintext, encoding="utf-8")
    os.chmod(cookie_file, 0o600)
    # Streamlink accepts individual HTTP cookies; retain the restricted file so
    # the exact session artifact is isolated and always cleaned in finally.
    flags: list[str] = []
    if "\t" in plaintext:
        for line in plaintext.splitlines():
            if line.startswith("#") or "\t" not in line: continue
            columns = line.split("\t")
            if len(columns) >= 7: flags.extend(["--http-cookie", f"{columns[5]}={columns[6]}"])
    elif plaintext.lower().startswith("bearer "):
        flags.extend(["--http-header", f"Authorization={plaintext}"])
    else:
        flags.extend(["--http-cookie", f"kick_session={plaintext}"])
    return flags, cookie_file

@shared_task
def record_stream(stream_id: str, normalized_url: str | None = None, owner_key: str | None = None) -> None:
    """Copy best-quality live media and reconnect only following an unexpected exit."""
    sid, settings = UUID(stream_id), get_settings()
    with SessionLocal() as db:
        stream = db.get(Stream, sid)
        if stream is None: return
        source_url, platform = stream.source_url, stream.platform
    client, chunks_dir = redis_client(), WORK_ROOT / stream_id / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    _set_status(sid, StreamStatus.recording, started_at=datetime.now(timezone.utc), stop_requested=False)
    ended = False
    cookie_file: Path | None = None
    try:
        session_flags, cookie_file = _session_capture_options(platform, chunks_dir)
        for attempt in range(settings.recording_max_reconnects + 1):
            command = ["streamlink", "--stdout", "--hls-live-restart", "--stream-segment-threads", "3", "--stream-timeout", "30", "--retry-max", "5", "--retry-open", "3"]
            if settings.egress_proxy_url: command.extend(["--http-proxy", settings.egress_proxy_url])
            command.extend(session_flags)
            command.extend([source_url, "best"])
            streamlink = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            ffmpeg = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-i", "pipe:0", "-c", "copy", "-f", "segment", "-segment_time", str(settings.recording_chunk_seconds), "-reset_timestamps", "1", str(chunks_dir / "chunk-%06d.ts")], stdin=streamlink.stdout, shell=False)
            streamlink.stdout.close()  # type: ignore[union-attr]
            stopped = False
            while ffmpeg.poll() is None:
                if client.exists(stop_key(stream_id)):
                    stopped = True; _terminate(ffmpeg); _terminate(streamlink); break
                time.sleep(1)
            streamlink.wait()
            stderr = streamlink.stderr.read() if streamlink.stderr else b""
            # Treat provider auth rejection as non-fatal: alert, then retry as guest.
            if cookie_file and (b"401" in (stderr or b"") or b"403" in (stderr or b"")):
                _expire_session(platform)
                try: cookie_file.unlink(missing_ok=True)
                finally: cookie_file = None
                session_flags = ["--twitch-disable-ads"] if platform == "twitch" else []
                continue
            if stopped or ffmpeg.returncode == 0:
                ended = True; break  # manual stop or provider EOF
            if attempt == settings.recording_max_reconnects: break
            _set_status(sid, StreamStatus.reconnecting)
            time.sleep(min(2 ** attempt, 300)); _set_status(sid, StreamStatus.recording)
        for chunk in sorted(chunks_dir.glob("*.ts")):
            upload_file(chunk, f"streams/{stream_id}/chunks/{chunk.name}")
        if not ended:
            _set_status(sid, StreamStatus.failed, error_message="Streamlink reconnect limit reached")
            if normalized_url: client.delete(active_key(normalized_url))
            _release_owner(owner_key, stream_id)
            return
        finalize_stream.delay(stream_id, normalized_url, owner_key)
    except Exception as error:
        _set_status(sid, StreamStatus.failed, error_message=f"Recording failed: {error}")
        if normalized_url: client.delete(active_key(normalized_url))
        _release_owner(owner_key, stream_id)
        raise
    finally:
        client.delete(stop_key(stream_id))
        if cookie_file:
            cookie_file.unlink(missing_ok=True)

@shared_task
def finalize_stream(stream_id: str, normalized_url: str | None = None, owner_key: str | None = None) -> None:
    sid, job_dir, settings = UUID(stream_id), WORK_ROOT / stream_id, get_settings()
    try:
        chunks = sorted((job_dir / "chunks").glob("*.ts"))
        if not chunks:
            _set_status(sid, StreamStatus.failed, error_message="No media chunks were produced"); return
        manifest, master = job_dir / "concat.txt", job_dir / "master.mp4"
        manifest.write_text("".join(f"file '{p.as_posix()}'\n" for p in chunks), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(master)], check=True, shell=False)
        with SessionLocal() as db:
            stream = db.get(Stream, sid)
            remove_music = bool(stream and stream.remove_music)
        if remove_music:
            from app.worker.audio_clean import clean_vocal_audio
            cleaned_master = job_dir / "master-vocals.mp4"
            if clean_vocal_audio(master, cleaned_master, job_dir / "audio-clean", settings.audio_clean_timeout_seconds):
                master = cleaned_master
        with SessionLocal() as db:
            stream = db.get(Stream, sid)
            enabled = bool(stream and stream.enable_end_screen)
            if enabled:
                from app.worker.outro import concat_command, render_outro
                recommendations = db.query(Stream).filter(Stream.id != sid, Stream.status == StreamStatus.ready).order_by(Stream.created_at.desc()).limit(2).all()
                outro, merged = job_dir / "outro.mp4", job_dir / "master-with-outro.mp4"
                logo_path = None
                if stream.archive_logo_key:
                    logo_path = job_dir / f"archive-logo{Path(stream.archive_logo_key).suffix or '.png'}"
                    download_file(stream.archive_logo_key, logo_path)
                render_outro(outro, stream.platform, stream.archive_channel_name or "Klipr Archive", stream.archive_tagline or "Archive Channel • Klipr.cloud", f"{stream.platform.upper()} • {stream.source_url}", recommendations, stream.outro_duration_seconds, logo_path)
                subprocess.run(concat_command(master, outro, merged), check=True, shell=False)
                master = merged
        key = f"streams/{stream_id}/master.mp4"; upload_file(master, key, "video/mp4")
        _set_status(sid, StreamStatus.processing, master_key=key, ended_at=datetime.now(timezone.utc))
        from app.worker.highlights import process_stream_highlights
        process_stream_highlights.delay(stream_id)
    finally:
        if normalized_url: redis_client().delete(active_key(normalized_url))
        _release_owner(owner_key, stream_id)
