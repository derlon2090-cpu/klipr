from PIL import Image
from app.worker.thumbnails import make_thumbnail, platform_color
def test_platform_colours_and_thumbnail_dimensions(tmp_path):
    vod, clip = tmp_path / "vod.png", tmp_path / "clip.png"
    make_thumbnail(None, vod, "twitch", "VOD", "Hello world"); make_thumbnail(None, clip, "kick", "CLIP", "مرحبا", portrait=True)
    assert platform_color("twitch") == "#9146FF" and platform_color("kick") == "#53FC18"
    assert Image.open(vod).size == (1280, 720) and Image.open(clip).size == (1080, 1920)
