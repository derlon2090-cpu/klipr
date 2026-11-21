import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.main import _vod_is_stale
from app.models import VodStatus
from app.worker.celery_app import celery_redis_url
from app.worker.vods import _session_download_options, extract_vod_metadata


def test_metadata_extraction_is_bounded_and_download_free():
    completed = SimpleNamespace(stdout=json.dumps({"title": "Ready now"}))
    with patch("app.worker.vods.subprocess.run", return_value=completed) as run:
        result = extract_vod_metadata("https://twitch.tv/videos/123", timeout=12)
    assert result["title"] == "Ready now"
    assert "--skip-download" in run.call_args.args[0]
    assert run.call_args.kwargs["timeout"] == 12


def test_kick_metadata_is_immediate_and_marks_subscriber_only():
    playback = SimpleNamespace(
        json=lambda: {"video_session": {"creator_id": 7, "video_title": "Instant", "video_duration": 42}},
        raise_for_status=lambda: None,
    )
    listing = SimpleNamespace(
        json=lambda: {"data": [{
            "id": "01a1f636-d8c0-74ed-b037-527fce8487ef",
            "title": "Instant", "duration": 42, "status": "sub_only",
            "channel": {"username": "Creator"}, "thumbnail": {"src": "https://image.test/x.jpg"},
        }]},
        raise_for_status=lambda: None,
    )
    with patch("app.worker.vods.requests.post", return_value=playback), patch("app.worker.vods.requests.get", return_value=listing):
        result = extract_vod_metadata("https://kick.com/creator/videos/01a1f636-d8c0-74ed-b037-527fce8487ef", timeout=12)
    assert result["title"] == "Instant"
    assert result["uploader"] == "Creator"
    assert result["availability"] == "subscriber_only"


def test_raw_kick_cookie_is_not_prefixed_twice(tmp_path):
    credential = SimpleNamespace(
        status="active", session_encrypted="encrypted", expires_at=None,
    )
    database = MagicMock()
    database.__enter__.return_value = database
    database.get.return_value = credential
    with patch("app.worker.vods.SessionLocal", return_value=database), patch("app.worker.vods.decrypt_secret", return_value="kick_session=secret"):
        options, cookie_file = _session_download_options("kick", tmp_path)
    assert options == ["--add-headers", "Cookie:kick_session=secret"]
    assert cookie_file is None


def test_celery_requires_verified_tls_for_managed_redis():
    assert celery_redis_url("rediss://user:secret@example.test:6380/0") == (
        "rediss://user:secret@example.test:6380/0?ssl_cert_reqs=required"
    )
    assert celery_redis_url("redis://localhost:6379/0") == "redis://localhost:6379/0"


def test_vod_job_is_marked_stale_after_twenty_minutes():
    stale = SimpleNamespace(
        status=VodStatus.fetching_metadata,
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=21),
    )
    fresh = SimpleNamespace(
        status=VodStatus.downloading,
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    assert _vod_is_stale(stale) is True
    assert _vod_is_stale(fresh) is False
