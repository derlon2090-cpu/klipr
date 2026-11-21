"""FFmpeg jobs for Production Studio.  All user files stay on the mounted volume."""
import json
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from celery import shared_task

from app.db import SessionLocal
from app.models import StudioRender, Vod
from app.storage import download_file
from app.worker.tasks import WORK_ROOT


def _update(render_id: UUID, **values: object) -> None:
    with SessionLocal() as db:
        render = db.get(StudioRender, render_id)
        if render:
            for key, value in values.items():
                setattr(render, key, value)
            db.commit()


def _has_audio(path: Path) -> bool:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", str(path)], capture_output=True, text=True, check=False)
    return bool(json.loads(result.stdout or "{}").get("streams"))


def _normal_input(path: Path, label: str, fps: int, audio: bool) -> list[str]:
    # Explicitly normalize SAR, geometry, FPS and audio.  apad gives image/video
    # assets without an audio stream a valid timeline for concat.
    vf = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p"
    if audio:
        return ["-i", str(path), "-filter_complex", f"[0:v]{vf}[{label}v];[0:a]aresample=48000,aresample=async=1[{label}a]", "-map", f"[{label}v]", "-map", f"[{label}a]"]
    return ["-i", str(path), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex", f"[0:v]{vf}[{label}v]", "-map", f"[{label}v]", "-map", "1:a"]


@shared_task(bind=True)
def render_studio(self, render_id: str) -> None:
    rid = UUID(render_id)
    with SessionLocal() as db:
        render, vod = db.get(StudioRender, rid), None
        if render:
            vod = db.get(Vod, render.vod_id)
        if not render or not vod or not vod.storage_key:
            _update(rid, status="failed", error_message="The selected VOD is no longer available.")
            return
        intro, outro = render.intro_path, render.outro_path
    job_dir = WORK_ROOT / "studio" / str(rid)
    source = job_dir / "vod.mp4"
    output = job_dir / "final.mp4"
    try:
        _update(rid, status="processing", progress=5, error_message=None)
        job_dir.mkdir(parents=True, exist_ok=True)
        download_file(vod.storage_key, source)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(source)], capture_output=True, text=True, check=False)
        raw_fps = probe.stdout.strip().split("/")
        fps = round(float(raw_fps[0]) / float(raw_fps[1])) if len(raw_fps) == 2 and raw_fps[1] != "0" else 30
        fps = max(24, min(60, fps))
        segments = [Path(p) for p in (intro, str(source), outro) if p]
        normalized: list[Path] = []
        for index, segment in enumerate(segments):
            normalized_file = job_dir / f"normalized-{index}.mp4"
            command = ["ffmpeg", "-y", "-i", str(segment)]
            if not _has_audio(segment): command += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            command += ["-filter_complex", f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v];[0:a]aresample=48000,aresample=async=1[a]" if _has_audio(segment) else f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v]", "-map", "[v]", "-map", "[a]" if _has_audio(segment) else "1:a", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", str(normalized_file)]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=7200)
            normalized.append(normalized_file)
            _update(rid, progress=20 + (index + 1) * 45 / len(segments))
        concat_list = job_dir / "concat.txt"
        concat_list.write_text("".join(f"file '{path.as_posix()}'\n" for path in normalized), encoding="utf-8")
        merged = job_dir / "merged.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(merged)], check=True, capture_output=True, text=True, timeout=7200)
        _update(rid, progress=75)
        with SessionLocal() as db:
            thumbnail = db.get(StudioRender, rid).thumbnail_path
        if thumbnail:
            subprocess.run(["ffmpeg", "-y", "-i", str(merged), "-i", thumbnail, "-map", "0", "-map", "1", "-c", "copy", "-c:v:1", "mjpeg", "-disposition:v:1", "attached_pic", "-movflags", "+faststart", str(output)], check=True, capture_output=True, text=True, timeout=7200)
        else:
            shutil.move(merged, output)
        _update(rid, status="ready", progress=100, output_path=str(output))
    except Exception as error:
        _update(rid, status="failed", error_message=str(error)[-1800:])
        raise
