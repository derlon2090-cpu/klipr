from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse
from uuid import UUID
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel
from sqlalchemy import func
from app.db import Base, engine, SessionLocal
from app.models import Clip, Stream, StreamStatus
from app.storage import presigned_download_url
from app.worker.highlights import process_stream_highlights
from app.worker.tasks import active_key, record_stream, redis_client, stop_key

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Klipr.cloud API", description="On-demand creator stream capture and AI clip studio.", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

class RecordRequest(BaseModel): stream_url: AnyHttpUrl

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
    process_stream_highlights.delay(str(stream_id))
    return {"id": str(stream_id), "status": StreamStatus.processing}
