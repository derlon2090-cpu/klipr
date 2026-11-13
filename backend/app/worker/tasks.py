"""Direct URL recording tasks. No polling or scheduler is used."""
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
import redis
from celery import shared_task
from app.config import get_settings
from app.db import SessionLocal
from app.models import Stream, StreamStatus
from app.storage import upload_file

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

@shared_task
def record_stream(stream_id: str, normalized_url: str | None = None, owner_key: str | None = None) -> None:
    """Copy best-quality live media and reconnect only following an unexpected exit."""
    sid, settings = UUID(stream_id), get_settings()
    with SessionLocal() as db:
        stream = db.get(Stream, sid)
        if stream is None: return
        source_url = stream.source_url
    client, chunks_dir = redis_client(), WORK_ROOT / stream_id / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    _set_status(sid, StreamStatus.recording, started_at=datetime.now(timezone.utc), stop_requested=False)
    ended = False
    try:
        for attempt in range(settings.recording_max_reconnects + 1):
            command = ["streamlink", "--stdout", "--hls-live-restart", "--stream-segment-threads", "3", "--stream-timeout", "30", "--retry-max", "5", "--retry-open", "3"]
            if settings.egress_proxy_url: command.extend(["--http-proxy", settings.egress_proxy_url])
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

@shared_task
def finalize_stream(stream_id: str, normalized_url: str | None = None, owner_key: str | None = None) -> None:
    sid, job_dir = UUID(stream_id), WORK_ROOT / stream_id
    try:
        chunks = sorted((job_dir / "chunks").glob("*.ts"))
        if not chunks:
            _set_status(sid, StreamStatus.failed, error_message="No media chunks were produced"); return
        manifest, master = job_dir / "concat.txt", job_dir / "master.mp4"
        manifest.write_text("".join(f"file '{p.as_posix()}'\n" for p in chunks), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(master)], check=True, shell=False)
        key = f"streams/{stream_id}/master.mp4"; upload_file(master, key, "video/mp4")
        _set_status(sid, StreamStatus.processing, master_key=key, ended_at=datetime.now(timezone.utc))
        from app.worker.highlights import process_stream_highlights
        process_stream_highlights.delay(stream_id)
    finally:
        if normalized_url: redis_client().delete(active_key(normalized_url))
        _release_owner(owner_key, stream_id)
