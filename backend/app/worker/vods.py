"""Finite VOD imports. Commands are argument arrays: URLs never enter a shell."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import UUID

from celery import shared_task

from app.db import SessionLocal
from app.models import Vod, VodStatus
from app.storage import upload_file

VOD_ROOT = Path("/var/lib/klipr/vods")
_PROGRESS = re.compile(r"^download:([\d.]+)%\|([^|]*)\|([^|]*)$")


def _update(vod_id: UUID, **fields: object) -> None:
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None:
            return
        for name, value in fields.items():
            setattr(item, name, value)
        db.commit()


def _metadata(url: str) -> dict:
    completed = subprocess.run(
        ["yt-dlp", "--dump-single-json", "--skip-download", "--no-playlist", url],
        capture_output=True, text=True, check=True, timeout=120,
    )
    return json.loads(completed.stdout)


def _save_thumbnail(url: str | None, directory: Path) -> str | None:
    if not url:
        return None
    target = directory / "thumbnail.jpg"
    try:
        request = Request(url, headers={"User-Agent": "Klipr.cloud VOD Vault/1.0"})
        with urlopen(request, timeout=30) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
        return str(target)
    except Exception:
        return None


@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def import_vod(self, vod_id: str) -> None:
    """Fetch metadata, download fragments concurrently, then make a seekable MP4 without re-encoding."""
    identifier = UUID(vod_id)
    with SessionLocal() as db:
        vod = db.get(Vod, identifier)
        if vod is None:
            return
        source_url, quality = vod.source_url, vod.quality
    directory = VOD_ROOT / vod_id
    directory.mkdir(parents=True, exist_ok=True)
    try:
        _update(identifier, status=VodStatus.fetching_metadata, progress=0, error_message=None)
        info = _metadata(source_url)
        title = str(info.get("title") or "Untitled VOD")[:500]
        uploader = str(info.get("uploader") or info.get("channel") or info.get("uploader_id") or "")[:160]
        duration = int(info["duration"]) if info.get("duration") else None
        thumbnail_path = _save_thumbnail(info.get("thumbnail"), directory)
        _update(identifier, title=title, streamer_name=uploader, duration_seconds=duration,
                thumbnail_url=info.get("thumbnail"), thumbnail_path=thumbnail_path,
                status=VodStatus.downloading)

        template = str(directory / "source.%(ext)s")
        format_selector = "best" if quality == "best" else quality
        command = [
            "yt-dlp", "--no-playlist", "--newline", "--no-part", "--concurrent-fragments", "8",
            "--merge-output-format", "mp4", "--format", format_selector,
            "--progress-template", "download:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
            "--output", template, source_url,
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            match = _PROGRESS.match(line.strip())
            if not match:
                continue
            eta_text = match.group(3).strip().replace("NA", "")
            try:
                eta = int(float(eta_text)) if eta_text else None
            except ValueError:
                eta = None
            _update(identifier, progress=min(99.0, float(match.group(1))), download_speed=match.group(2).strip() or None,
                    eta_seconds=eta)
        if process.wait() != 0:
            raise RuntimeError("yt-dlp could not download this VOD. Check that it is public and available.")

        candidates = [path for path in directory.glob("source.*") if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".ts", ".m4v"}]
        if not candidates:
            raise RuntimeError("The download completed without a playable media file.")
        source = max(candidates, key=lambda path: path.stat().st_size)
        final = directory / "vod.mp4"
        _update(identifier, status=VodStatus.remuxing, progress=99, download_speed=None, eta_seconds=None)
        subprocess.run(["ffmpeg", "-y", "-i", str(source), "-map", "0", "-c", "copy", "-movflags", "+faststart", str(final)],
                       check=True, capture_output=True, text=True, timeout=3600)
        storage_key = f"vods/{vod_id}/vod.mp4"
        upload_file(final, storage_key, "video/mp4")
        thumbnail_key = None
        if thumbnail_path:
            thumbnail_key = f"vods/{vod_id}/thumbnail.jpg"
            upload_file(Path(thumbnail_path), thumbnail_key, "image/jpeg")
        _update(identifier, status=VodStatus.ready, progress=100, storage_key=storage_key,
                thumbnail_key=thumbnail_key, local_path=None, thumbnail_path=None,
                file_size=final.stat().st_size, download_speed=None, eta_seconds=None)
        shutil.rmtree(directory, ignore_errors=True)
    except Exception as error:
        _update(identifier, status=VodStatus.failed, error_message=str(error)[:2000], download_speed=None, eta_seconds=None)
        raise
