import pytest
from fastapi import HTTPException

from app.main import normalize_vod_url


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=example",
    "https://vimeo.com/123456",
    "https://kick.com/creator/videos/01a1f636-d8c0-74ed-b037-527fce8487ef",
])
def test_public_video_platforms_are_accepted(url):
    assert normalize_vod_url(url)[1].startswith("https://")


@pytest.mark.parametrize("url", ["https://localhost/video", "https://127.0.0.1/video", "http://youtube.com/video"])
def test_private_and_insecure_vod_urls_are_rejected(url):
    with pytest.raises(HTTPException):
        normalize_vod_url(url)
