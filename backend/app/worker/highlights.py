"""Whisper transcription, energy ranking, and vertical clip rendering."""
from __future__ import annotations
import math, shutil, subprocess, wave
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
import numpy as np
from celery import shared_task
from faster_whisper import WhisperModel
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
    config = get_settings()
    model = WhisperModel(config.whisper_model, device=config.whisper_device, compute_type=config.whisper_compute_type)
    segments, _ = model.transcribe(str(wav), word_timestamps=True, vad_filter=True)
    return [Word(word.start, word.end, word.word.strip()) for segment in segments for word in (segment.words or [])]

def choose_windows(energy: list[float], duration: float, words: list[Word]) -> list[Window]:
    candidates: list[Window] = []
    for index in range(len(energy)):
        center = index * 5 + 2.5
        start = max(0.0, min(center - 22.5, max(0.0, duration - 45)))
        end = min(duration, start + 45)
        rms = float(np.mean(energy[int(start // 5):int(math.ceil(end / 5))] or [0.0]))
        density = min(sum(word.start < end and word.end > start for word in words) / max(end - start, 1), 4) / 4
        candidates.append(Window(start, end, 0.75 * rms + 0.25 * density))
    chosen: list[Window] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if all(candidate.end <= item.start or candidate.start >= item.end for item in chosen):
            chosen.append(candidate)
        if len(chosen) == 3:
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
        text = " ".join(word.text for word in group).replace("{", r"\{").replace("}", r"\}").strip()
        if text:
            snippet.append(text)
            events.append(f"Dialogue: 0,{ass_time(group[0].start-start)},{ass_time(group[-1].end-start)},Default,,0,0,0,,{text}")
    destination.write_text("\n".join(["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding", "Style: Default,Arial,62,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,70,70,430,1", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text", *events]), encoding="utf-8")
    return " ".join(snippet)[:1000]

def render_vertical(vod: Path, ass: Path, window: Window, destination: Path) -> None:
    ass_path = ass.as_posix().replace("'", r"\'").replace(":", r"\:")
    graph = ("[0:v]split=2[bgsrc][fgsrc];[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[bg];" "[fgsrc]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles='" + ass_path + "'[v]")
    run(["ffmpeg", "-y", "-ss", f"{window.start:.3f}", "-t", f"{window.end-window.start:.3f}", "-i", str(vod), "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(destination)])

@shared_task
def process_stream_highlights(stream_id: str) -> None:
    sid = UUID(stream_id)
    with SessionLocal() as db:
        stream = db.get(Stream, sid)
        if stream is None or not stream.master_key:
            raise ValueError("A completed master VOD is required")
        master_key = stream.master_key
    job_dir = WORK_ROOT / stream_id / "highlight-processing"
    vod, wav = job_dir / "master.mp4", job_dir / "audio.wav"
    _set_status(sid, StreamStatus.processing)
    try:
        download_file(master_key, vod)
        extract_audio(vod, wav)
        energy, duration = rms_windows(wav)
        words = transcribe(wav)
        windows = choose_windows(energy, duration, words)
        with SessionLocal() as db:
            db.query(Clip).filter(Clip.stream_id == sid).delete()
            for index, window in enumerate(windows, 1):
                ass, output = job_dir / f"highlight-{index}.ass", job_dir / f"highlight-{index}.mp4"
                snippet = write_ass(words, window.start, window.end, ass)
                render_vertical(vod, ass, window, output)
                key = f"clips/{stream_id}/highlight-{index}.mp4"
                upload_file(output, key, "video/mp4")
                db.add(Clip(stream_id=sid, start_seconds=window.start, end_seconds=window.end, score=window.score, vertical_key=key, transcript=snippet))
            db.commit()
        _set_status(sid, StreamStatus.ready)
    except Exception as error:
        _set_status(sid, StreamStatus.failed, error_message=f"Highlight processing failed: {error}")
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

extract_highlights = process_stream_highlights
