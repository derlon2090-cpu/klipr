import asyncio
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from starlette.datastructures import UploadFile

from app.main import upload_branding_thumbnail
from app.worker.thumbnails import make_thumbnail, platform_color


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
