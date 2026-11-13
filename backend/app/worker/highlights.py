"""Whisper transcription, energy ranking, and vertical clip rendering."""
from __future__ import annotations
import json, math, shutil, subprocess, wave
from urllib.request import Request as UrlRequest, urlopen
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
import numpy as np
from celery import shared_task
from app.config import get_settings
from app.db import SessionLocal
from app.models import Clip, Stream, StreamStatus
from app.storage import download_file, upload_file
from .tasks import WORK_ROOT, _set_status

@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str

@dataclass(frozen=True)
class Window:
    start: float
    end: float
    score: float

def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True, shell=False)

def extract_audio(vod: Path, wav: Path) -> None:
    run(["ffmpeg", "-y", "-i", str(vod), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])

def rms_windows(wav: Path, seconds: int = 5) -> tuple[list[float], float]:
    with wave.open(str(wav), "rb") as reader:
        rate, frames = reader.getframerate(), reader.getnframes()
        samples = np.frombuffer(reader.readframes(frames), dtype=np.int16).astype(np.float32) / 32768.0
    buckets = max(1, math.ceil(len(samples) / (rate * seconds)))
    values = [float(np.sqrt(np.mean(block * block))) for block in np.array_split(samples, buckets) if len(block)]
    maximum = max(values, default=0.0)
    return [value / maximum if maximum else 0.0 for value in values], frames / rate

def transcribe(wav: Path) -> list[Word]:
    from faster_whisper import WhisperModel
    config = get_settings()
    model = WhisperModel(config.whisper_model, device=config.whisper_device, compute_type=config.whisper_compute_type)
    segments, _ = model.transcribe(str(wav), word_timestamps=True, vad_filter=True)
    return [Word(word.start, word.end, word.word.strip()) for segment in segments for word in (segment.words or [])]

def choose_windows(energy: list[float], duration: float, words: list[Word], target_seconds: int = 45, max_clips: int = 3) -> list[Window]:
    candidates: list[Window] = []
    for index in range(len(energy)):
        center = index * 5 + 2.5
        start = max(0.0, min(center - target_seconds / 2, max(0.0, duration - target_seconds)))
        end = min(duration, start + target_seconds)
        rms = float(np.mean(energy[int(start // 5):int(math.ceil(end / 5))] or [0.0]))
        density = min(sum(word.start < end and word.end > start for word in words) / max(end - start, 1), 4) / 4
        candidates.append(Window(start, end, 0.75 * rms + 0.25 * density))
    chosen: list[Window] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if all(candidate.end <= item.start or candidate.start >= item.end for item in chosen):
            chosen.append(candidate)
        if len(chosen) == max_clips:
            break
    return sorted(chosen, key=lambda item: item.start)

def ass_time(seconds: float) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, remainder = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{remainder:05.2f}"

def write_ass(words: list[Word], start: float, end: float, destination: Path) -> str:
    relevant = [word for word in words if word.start < end and word.end > start]
    events, snippet = [], []
    for offset in range(0, len(relevant), 7):
        group = relevant[offset:offset + 7]
        plain = " ".join(word.text for word in group).replace("{", r"\{").replace("}", r"\}").strip()
        # ASS karaoke changes the primary colour exactly while each word is spoken.
        karaoke_parts = []
        for word in group:
            escaped_word = word.text.replace("{", r"\{").replace("}", r"\}")
            karaoke_parts.append(f"{{\\kf{max(1, round((word.end-word.start)*100))}}}{escaped_word}")
        karaoke = " ".join(karaoke_parts).strip()
        if plain:
            snippet.append(plain)
            events.append(f"Dialogue: 0,{ass_time(group[0].start-start)},{ass_time(group[-1].end-start)},Default,,0,0,0,,{karaoke}")
    destination.write_text("\n".join(["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding", "Style: Default,Arial,62,&H0000D7FF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,70,70,430,1", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text", *events]), encoding="utf-8")
    return " ".join(snippet)[:1000]

def find_facecam_crop(vod: Path, window: Window) -> tuple[int, int, int, int] | None:
    """Sample video frames and select a stable 16:9 crop around the largest face."""
    try:
        import cv2
        capture = cv2.VideoCapture(str(vod))
        capture.set(cv2.CAP_PROP_POS_MSEC, window.start * 1000)
        classifier = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        candidates: list[tuple[int, int, int, int]] = []
        for _ in range(8):
            ok, frame = capture.read()
            if not ok: break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = classifier.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(40, 40))
            if len(faces): candidates.append(max(faces, key=lambda face: face[2] * face[3]))
            capture.set(cv2.CAP_PROP_POS_MSEC, capture.get(cv2.CAP_PROP_POS_MSEC) + 1500)
        capture.release()
        if not candidates: return None
        frame_h, frame_w = frame.shape[:2]
        x, y, width, height = candidates[len(candidates) // 2]
        crop_h = min(frame_h, max(height * 4, int(frame_w * 9 / 16)))
        crop_w = min(frame_w, int(crop_h * 16 / 9))
        crop_h, crop_w = int(crop_w * 9 / 16), crop_w
        crop_x = max(0, min(frame_w - crop_w, int(x + width / 2 - crop_w / 2)))
        crop_y = max(0, min(frame_h - crop_h, int(y + height / 2 - crop_h / 2)))
        return crop_x, crop_y, crop_w, crop_h
    except Exception:
        return None

def build_filter_graph(ass: Path, layout_mode: str, facecam_crop: tuple[int, int, int, int] | None = None) -> str:
    ass_path = ass.as_posix().replace("'", r"\'").replace(":", r"\:")
    if layout_mode == "split" and facecam_crop:
            x, y, width, height = facecam_crop
            graph = f"[0:v]split=2[cam][game];[cam]crop={width}:{height}:{x}:{y},scale=1080:960[top];[game]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom];[top][bottom]vstack=inputs=2,subtitles='{ass_path}'[v]"
    else: graph = f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles='{ass_path}'[v]"
    return graph

def render_vertical(vod: Path, ass: Path, window: Window, destination: Path, layout_mode: str) -> None:
    graph = build_filter_graph(ass, layout_mode, find_facecam_crop(vod, window) if layout_mode == "split" else None)
    run(["ffmpeg", "-y", "-ss", f"{window.start:.3f}", "-t", f"{window.end-window.start:.3f}", "-i", str(vod), "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(destination)])

@shared_task
def process_stream_highlights(stream_id: str, max_clips: int = 3) -> None:
    sid = UUID(stream_id)
    with SessionLocal() as db:
        stream = db.get(Stream, sid)
        if stream is None or not stream.master_key:
            raise ValueError("A completed master VOD is required")
        master_key = stream.master_key
        layout_mode, webhook_url = stream.layout_mode, stream.discord_webhook_url
        target_seconds, headline, embed_intro, platform = stream.target_clip_duration, stream.custom_headline or "", stream.embed_intro_cover, stream.platform
    job_dir = WORK_ROOT / stream_id / "highlight-processing"
    vod, wav = job_dir / "master.mp4", job_dir / "audio.wav"
    _set_status(sid, StreamStatus.processing)
    try:
        download_file(master_key, vod)
        extract_audio(vod, wav)
        energy, duration = rms_windows(wav)
        words = transcribe(wav)
        windows = choose_windows(energy, duration, words, target_seconds, max_clips)
        with SessionLocal() as db:
            db.query(Clip).filter(Clip.stream_id == sid).delete()
            for index, window in enumerate(windows, 1):
                ass, output = job_dir / f"highlight-{index}.ass", job_dir / f"highlight-{index}.mp4"
                snippet = write_ass(words, window.start, window.end, ass)
                render_vertical(vod, ass, window, output, layout_mode)
                key = f"clips/{stream_id}/highlight-{index}.mp4"
                upload_file(output, key, "video/mp4")
                from .thumbnails import make_thumbnail
                cover = job_dir / f"highlight-{index}.png"; make_thumbnail(None, cover, platform, "CLIP", headline or snippet[:42], portrait=True)
                thumb_key = f"clips/{stream_id}/highlight-{index}.png"; upload_file(cover, thumb_key, "image/png")
                db.add(Clip(stream_id=sid, start_seconds=window.start, end_seconds=window.end, score=window.score, vertical_key=key, thumbnail_key=thumb_key, transcript=snippet))
            db.commit()
        _set_status(sid, StreamStatus.ready)
        send_discord_notification(stream_id, webhook_url, len(windows))
    except Exception as error:
        _set_status(sid, StreamStatus.failed, error_message=f"Highlight processing failed: {error}")
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

extract_highlights = process_stream_highlights

def send_discord_notification(stream_id: str, webhook_url: str | None, clip_count: int) -> None:
    if not webhook_url: return
    studio = get_settings().klipr_studio_url.rstrip("/") + f"/dashboard/streams/{stream_id}"
    body = {"embeds": [{"title": "Klipr Studio clips are ready", "description": f"{clip_count} viral-ready clip(s) are available.", "url": studio, "color": 65280, "fields": [{"name": "Open Studio", "value": studio}]}]}
    request = UrlRequest(webhook_url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "Klipr.cloud/1.0"}, method="POST")
    try:
        with urlopen(request, timeout=8): pass
    except Exception:
        # Notification failure must never discard an otherwise completed render.
        return
