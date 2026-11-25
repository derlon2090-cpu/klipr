"""FFmpeg jobs for Production Studio.  All user files stay on the mounted volume."""
import json
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from celery import shared_task

from app.db import SessionLocal
from app.models import ArchiveBranding, StudioRender, Vod
from app.storage import download_file, presigned_download_url, upload_file
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


def _duration_seconds(path: Path) -> float:
    """Return a verified media duration instead of trusting container timestamps."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError("The selected video range could not be verified") from error
    if duration <= 0:
        raise RuntimeError("The selected video range is empty or invalid")
    return duration


def _require_workspace(job_dir: Path, required_bytes: int) -> None:
    """Fail before a large export can exhaust the worker disk and corrupt PostgreSQL."""
    free_bytes = shutil.disk_usage(job_dir).free
    if free_bytes < required_bytes:
        required_gib = required_bytes / (1024 ** 3)
        free_gib = free_bytes / (1024 ** 3)
        raise RuntimeError(
            f"Not enough temporary workspace for this range ({free_gib:.0f} GiB free; "
            f"{required_gib:.0f} GiB required). Choose a shorter end time and export it in parts."
        )


def _cleanup_intermediates(job_dir: Path, output: Path) -> None:
    """Keep only the downloadable result on the persistent media volume."""
    for path in job_dir.iterdir():
        if path != output and path.is_file():
            path.unlink(missing_ok=True)


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
        intro, outro, export_quality = render.intro_path, render.outro_path, render.export_quality
        start_seconds, end_seconds = render.start_seconds, render.end_seconds
        branding = db.get(ArchiveBranding, 1)
    job_dir = WORK_ROOT / "studio" / str(rid)
    source = job_dir / "vod.mp4"
    output = job_dir / "final.mp4"
    try:
        _update(rid, status="processing", progress=5, error_message=None)
        job_dir.mkdir(parents=True, exist_ok=True)
        if not intro and branding and branding.default_intro_key:
            intro_file = job_dir / "default-intro.mp4"; download_file(branding.default_intro_key, intro_file); intro = str(intro_file)
        if not outro and branding and branding.default_outro_key:
            outro_file = job_dir / "default-outro.mp4"; download_file(branding.default_outro_key, outro_file); outro = str(outro_file)
        expected_seconds = max(1.0, (end_seconds or vod.duration_seconds or 1) - (start_seconds or 0))
        # The original range and its final copy coexist while FFmpeg concatenates.
        # Reserve both before downloading anything; this prevents a full disk from
        # leaving a truncated MP4 with bogus (for example 30-hour) timestamps.
        source_estimate = int((vod.file_size or 0) * expected_seconds / max(1, vod.duration_seconds or expected_seconds))
        if intro or outro:
            _require_workspace(job_dir, max(8 * 1024 ** 3, source_estimate * 2 + 2 * 1024 ** 3))
        source_url = presigned_download_url(vod.storage_key)
        trim_command = ["ffmpeg", "-y"]
        if start_seconds is not None: trim_command += ["-ss", str(start_seconds)]
        trim_command += ["-i", source_url]
        if end_seconds is not None: trim_command += ["-t", str(end_seconds - (start_seconds or 0))]
        trim_command += ["-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-fflags", "+genpts", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(source)]
        trim_process = subprocess.Popen(trim_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        assert trim_process.stdout is not None
        for line in trim_process.stdout:
            if line.startswith("out_time_ms="):
                try:
                    elapsed = int(line.split("=", 1)[1]) / 1_000_000
                    _update(rid, progress=min(55, 5 + elapsed / expected_seconds * 50))
                except ValueError:
                    pass
        if trim_process.wait() != 0:
            raise RuntimeError("Unable to extract the selected time range")
        source_duration = _duration_seconds(source)
        duration_tolerance = max(12.0, expected_seconds * 0.02)
        if abs(source_duration - expected_seconds) > duration_tolerance:
            raise RuntimeError(
                f"The extracted range duration is invalid ({source_duration:.1f}s; expected {expected_seconds:.1f}s)."
            )
        _update(rid, progress=65)
        # With no intro/outro, preserve the original VOD without re-encoding.
        if not intro and not outro and export_quality == "original":
            shutil.move(source, output)
            _cleanup_intermediates(job_dir, output)
            _update(rid, status="ready", progress=100, output_path=str(output), intro_path=None, outro_path=None)
            return
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(source)], capture_output=True, text=True, check=False)
        raw_fps = probe.stdout.strip().split("/")
        source_fps = round(float(raw_fps[0]) / float(raw_fps[1])) if len(raw_fps) == 2 and raw_fps[1] != "0" else 30
        fps = 60 if export_quality == "4k" else max(24, min(60, source_fps))
        width, height = (3840, 2160) if export_quality == "4k" else (1920, 1080)
        video_options = ["-c:v", "libx264", "-preset", "medium", "-crf", "16"] if export_quality == "4k" else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        audio_options = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"] if export_quality == "4k" else ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        segments = [Path(p) for p in (intro, str(source), outro) if p]
        normalized: list[Path] = []
        for index, segment in enumerate(segments):
            # The selected VOD is already H.264/AAC at its native quality.
            # Never re-encode a multi-hour source merely to concatenate it
            # with the short branded clips.
            if segment == source and export_quality == "original":
                normalized.append(source)
                _update(rid, progress=70)
                continue
            normalized_file = job_dir / f"normalized-{index}.mp4"
            command = ["ffmpeg", "-y", "-i", str(segment)]
            if not _has_audio(segment): command += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            sharpen = ",unsharp=5:5:0.5:5:5:0" if export_quality == "4k" else ""
            video_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}{sharpen},format=yuv420p"
            command += ["-filter_complex", f"[0:v]{video_filter}[v];[0:a]aresample=48000,aresample=async=1[a]" if _has_audio(segment) else f"[0:v]{video_filter}[v]", "-map", "[v]", "-map", "[a]" if _has_audio(segment) else "1:a", *video_options, *audio_options, "-movflags", "+faststart", str(normalized_file)]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=86400 if export_quality == "4k" else 21600)
            normalized.append(normalized_file)
            _update(rid, progress=20 + (index + 1) * 45 / len(segments))
        concat_list = job_dir / "concat.txt"
        concat_list.write_text("".join(f"file '{path.as_posix()}'\n" for path in normalized), encoding="utf-8")
        merged = job_dir / "merged.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(merged),
        ], check=True, capture_output=True, text=True, timeout=7200)
        expected_final_duration = sum(_duration_seconds(path) for path in normalized)
        final_duration = _duration_seconds(merged)
        final_tolerance = max(15.0, expected_final_duration * 0.02)
        if abs(final_duration - expected_final_duration) > final_tolerance:
            raise RuntimeError(
                f"The merged file duration is invalid ({final_duration:.1f}s; expected {expected_final_duration:.1f}s)."
            )
        _update(rid, progress=75)
        shutil.move(merged, output)
        _update(rid, progress=92)
        storage_key = f"editorial/{vod.id}/{rid}.mp4"
        upload_file(output, storage_key, "video/mp4")
        _cleanup_intermediates(job_dir, output)
        _update(rid, status="ready", progress=100, output_path=str(output), storage_key=storage_key, intro_path=None, outro_path=None)
    except Exception as error:
        _update(rid, status="failed", error_message=str(error)[-1800:])
        # A failed job is never a reusable source.  Removing it immediately
        # protects PostgreSQL and future exports from disk exhaustion.
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
