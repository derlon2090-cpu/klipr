import asyncio
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from starlette.datastructures import UploadFile

from app.main import upload_branding_thumbnail
from app.worker.thumbnails import make_thumbnail, platform_color
from app.worker.smart_thumbnails import _fallback_moments, _moment_samples, _visual_score


def test_platform_colours_and_thumbnail_dimensions(tmp_path):
    vod, clip = tmp_path / "vod.png", tmp_path / "clip.png"
    make_thumbnail(None, vod, "twitch", "VOD", "Hello world"); make_thumbnail(None, clip, "kick", "CLIP", "مرحبا", portrait=True)
    assert platform_color("twitch") == "#9146FF" and platform_color("kick") == "#53FC18"
    assert Image.open(vod).size == (1280, 720) and Image.open(clip).size == (1080, 1920)


def test_branding_thumbnail_response_does_not_read_detached_model():
    class Branding:
        detached = False
        _enabled = False
        default_thumbnail_key = None

        @property
        def use_default_thumbnail(self):
            if self.detached:
                raise RuntimeError("detached model read")
            return self._enabled

        @use_default_thumbnail.setter
        def use_default_thumbnail(self, value):
            self._enabled = value

    item = Branding()

    class Database:
        def __enter__(self): return self
        def __exit__(self, *_args): item.detached = True
        def add(self, _value): pass
        def commit(self): pass

    upload = UploadFile(filename="thumb.png", file=BytesIO(b"\x89PNG\r\n\x1a\ncontent"))
    with patch("app.main.SessionLocal", return_value=Database()), \
         patch("app.main._branding", return_value=item), \
         patch("app.main.upload_file"), \
         patch("app.main.presigned_download_url", return_value="https://signed.test/thumb"):
        result = asyncio.run(upload_branding_thumbnail(upload, "vod"))
    assert result["use_default_thumbnail"] is True


def test_smart_thumbnail_samples_are_in_the_highlight_not_a_random_vod_position():
    samples = _moment_samples(100, 120, 3600)
    assert len(samples) == 4
    assert all(100 < sample < 120 for sample in samples)
    fallback = _fallback_moments(600, 3)
    assert len(fallback) == 3
    assert fallback[0][1] < fallback[1][0] < fallback[2][0]


def test_smart_thumbnail_visual_score_rejects_a_blank_frame(tmp_path):
    blank, detailed = tmp_path / "blank.jpg", tmp_path / "detailed.jpg"
    Image.new("RGB", (320, 180), "black").save(blank)
    patterned = Image.new("RGB", (320, 180), "black")
    pixels = patterned.load()
    for x in range(320):
        for y in range(180):
            pixels[x, y] = (255, 50, 50) if (x // 12 + y // 12) % 2 else (20, 180, 255)
    patterned.save(detailed)
    assert _visual_score(detailed) > _visual_score(blank)
