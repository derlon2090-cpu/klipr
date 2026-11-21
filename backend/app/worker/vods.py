"""Finite VOD imports. Commands are argument arrays: URLs never enter a shell."""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import UUID

import requests
from celery import shared_task

from app.core.crypto import decrypt_secret
from app.db import SessionLocal
from app.models import SessionCredential, Vod, VodStatus
from app.storage import upload_file

VOD_ROOT = Path("/var/lib/klipr/vods")
_PROGRESS = re.compile(r"^download:([\d.]+)%\|([^|]*)\|([^|]*)$")
_KICK_VIDEO = re.compile(r"^https?://(?:www\.)?kick\.com/[^/]+/videos/([0-9a-f-]{36})(?:[/?#]|$)", re.I)
_KICK_API = "https://web.kick.com/api/v1"


def _update(vod_id: UUID, **fields: object) -> None:
    with SessionLocal() as db:
        item = db.get(Vod, vod_id)
        if item is None:
            return
        for name, value in fields.items():
            setattr(item, name, value)
        db.commit()


def _kick_metadata(url: str, timeout: int) -> dict | None:
    """Use Kick's small JSON endpoints so metadata does not wait on yt-dlp."""
    match = _KICK_VIDEO.match(url)
    if not match:
        return None
    video_id = match.group(1)
    headers = {"User-Agent": "Mozilla/5.0 Klipr.cloud/1.0"}
    payload = {
        "video_player": {"player": {}},
        "video_session": {},
        "user_session": {"non_personalised_ads": True},
    }
    playback = requests.post(
        f"{_KICK_API}/stream/{video_id}/playback",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    playback.raise_for_status()
    session = playback.json().get("video_session") or {}
    creator_id = session.get("creator_id")
    video: dict = {}
    if creator_id:
        listing = requests.get(f"{_KICK_API}/channels/{creator_id}/videos", headers=headers, timeout=timeout)
        listing.raise_for_status()
        video = next((item for item in listing.json().get("data", []) if item.get("id") == video_id), {})
    channel = video.get("channel") or {}
    thumbnail = video.get("thumbnail") or {}
    status = video.get("status")
    return {
        "id": video_id,
        "title": video.get("title") or session.get("video_title"),
        "uploader": channel.get("username") or session.get("video_series"),
        "channel": channel.get("slug"),
        "duration": video.get("duration") or session.get("video_duration"),
        "thumbnail": thumbnail.get("src"),
        "availability": "subscriber_only" if status == "sub_only" else "public",
    }


def extract_vod_metadata(url: str, timeout: int = 45) -> dict:
    """Fetch the small metadata document without downloading media."""
    kick = _kick_metadata(url, timeout)
    if kick is not None:
        return kick
    completed = subprocess.run(
        ["yt-dlp", "--force-ipv4", "--dump-single-json", "--skip-download", "--no-playlist", url],
        capture_output=True, text=True, check=True, timeout=timeout,
    )
    return json.loads(completed.stdout)


def _session_download_options(platform: str, directory: Path) -> tuple[list[str], Path | None, dict[str, str]]:
    """Convert an encrypted Session Vault entry into yt-dlp and HTTP headers."""
    if platform not in {"kick", "twitch"}:
        return [], None, {}
    with SessionLocal() as db:
        credential = db.get(SessionCredential, platform)
        if not credential or credential.status != "active" or not credential.session_encrypted:
            return [], None, {}
        if credential.expires_at and credential.expires_at <= datetime.now(timezone.utc):
            credential.status = "expired"
            db.commit()
            return [], None, {}
        plaintext = decrypt_secret(credential.session_encrypted)
    if "\t" in plaintext:
        cookie_file = directory / f"{platform}_cookies.txt"
        cookie_file.write_text(plaintext, encoding="utf-8")
        os.chmod(cookie_file, 0o600)
        cookies = []
        for line in plaintext.splitlines():
            if line.startswith("#") or "\t" not in line:
                continue
            columns = line.split("\t")
            if len(columns) >= 7:
                cookies.append(f"{columns[5]}={columns[6]}")
        headers = {"Cookie": "; ".join(cookies)} if cookies else {}
        return ["--cookies", str(cookie_file)], cookie_file, headers
    if plaintext.lower().startswith("bearer "):
        return ["--add-headers", f"Authorization:{plaintext}"], None, {"Authorization": plaintext}
    cookie_header = plaintext if "=" in plaintext else f"kick_session={plaintext}"
    return ["--add-headers", f"Cookie:{cookie_header}"], None, {"Cookie": cookie_header}


def _kick_playback_url(url: str, request_headers: dict[str, str], timeout: int = 15) -> str:
    """Resolve a Kick page once, then download its signed HLS URL directly."""
    match = _KICK_VIDEO.match(url)
    if not match:
        return url
    headers = {"User-Agent": "Mozilla/5.0 Klipr.cloud/1.0", **request_headers}
    payload = {
        "video_player": {"player": {}},
        "video_session": {},
        "user_session": {"non_personalised_ads": True},
    }
    response = requests.post(
        f"{_KICK_API}/stream/{match.group(1)}/playback",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    playback = response.json().get("playback_url") or {}
    resolved = playback.get("vod") if isinstance(playback, dict) else playback
    if not resolved:
        raise RuntimeError("Kick did not return a playable VOD URL. Check the saved session.")
    return str(resolved)


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


def _extract_best_frame(video: Path, directory: Path) -> str | None:
    """Fallback cover when providers do not expose artwork.

    FFmpeg's thumbnail filter selects a representative frame from a spread of
    samples, avoiding the first/black frame common in archived broadcasts.
    """
    target = directory / "thumbnail.jpg"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", "00:00:12", "-i", str(video), "-vf",
            "fps=1/12,thumbnail=20,scale=1280:-2", "-frames:v", "1", "-q:v", "2", str(target),
        ], check=True, capture_output=True, text=True, timeout=180)
        return str(target) if target.exists() and target.stat().st_size else None
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
        source_url, quality, platform = vod.source_url, vod.quality, vod.platform
        title, uploader = vod.title, vod.streamer_name
        duration, thumbnail_url = vod.duration_seconds, vod.thumbnail_url
    directory = VOD_ROOT / vod_id
    directory.mkdir(parents=True, exist_ok=True)
    cookie_file: Path | None = None
    try:
        if not title:
            _update(identifier, status=VodStatus.fetching_metadata, progress=0, error_message=None)
            info = extract_vod_metadata(source_url)
            title = str(info.get("title") or "Untitled VOD")[:500]
            uploader = str(info.get("uploader") or info.get("channel") or info.get("uploader_id") or "")[:160]
            duration = int(info["duration"]) if info.get("duration") else None
            thumbnail_url = info.get("thumbnail")
        thumbnail_path = _save_thumbnail(thumbnail_url, directory)
        _update(identifier, title=title, streamer_name=uploader, duration_seconds=duration,
                thumbnail_url=thumbnail_url, thumbnail_path=thumbnail_path,
                status=VodStatus.downloading, progress=1, error_message=None)

        template = str(directory / "source.%(ext)s")
        format_selector = "best" if quality == "best" else quality
        session_options, cookie_file, request_headers = _session_download_options(platform, directory)
        download_url = _kick_playback_url(source_url, request_headers) if platform == "kick" else source_url
        command = [
            "yt-dlp", "--force-ipv4", "--no-playlist", "--newline", "--no-part", "--concurrent-fragments", "8",
            "--merge-output-format", "mp4", "--format", format_selector,
            "--progress-template", "download:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
            "--output", template,
        ]
        command.extend(session_options)
        command.append(download_url)
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
        # Prefer platform artwork, but never make the VOD card depend on it.
        thumbnail_path = thumbnail_path or _extract_best_frame(final, directory)
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
    finally:
        if cookie_file:
            cookie_file.unlink(missing_ok=True)
