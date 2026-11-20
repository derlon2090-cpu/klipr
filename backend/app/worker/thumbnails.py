"""Deterministic branded VOD/Short cover compositor."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PLATFORM_COLORS = {"twitch": "#9146FF", "kick": "#53FC18"}
def platform_color(platform: str) -> str: return PLATFORM_COLORS.get(platform, PLATFORM_COLORS["kick"])
def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if Path(path).exists(): return ImageFont.truetype(path, size)
    return ImageFont.load_default()
def make_thumbnail(frame: Path | None, destination: Path, platform: str, label: str, headline: str, portrait: bool = False) -> None:
    size = (1080, 1920) if portrait else (1280, 720); color = platform_color(platform)
    try: base = Image.open(frame).convert("RGB").resize(size) if frame else Image.new("RGB", size, "#101014")
    except Exception: base = Image.new("RGB", size, "#101014")
    base = base.filter(ImageFilter.GaussianBlur(0.35)); draw = ImageDraw.Draw(base); margin = 28
    draw.rounded_rectangle((margin, margin, size[0]-margin, size[1]-margin), radius=34, outline=color, width=18)
    draw.rounded_rectangle((55, 55, 275, 125), radius=22, fill="#111116", outline=color, width=4); draw.text((78, 72), f"{platform.upper()} {label}", font=_font(25), fill="white")
    # The Full HD mark is deliberately VOD-only: Shorts retain their clean 9:16 composition.
    headline_top = 155
    if not portrait:
        draw.rounded_rectangle((55, 140, 225, 190), radius=16, fill="#111116e8", outline=color, width=3)
        draw.text((76, 153), "1080 FULL HD", font=_font(18), fill="white")
        headline_top = 220
    text = headline[:80] or "LIVE HIGHLIGHT"; box = draw.textbbox((0,0), text, font=_font(42)); w = box[2]
    x = max(55, (size[0]-w)//2); draw.rounded_rectangle((x-25, headline_top, x+w+25, headline_top+75), radius=28, fill="#0b0b0ddd", outline=color, width=3); draw.text((x, headline_top+14), text, font=_font(42), fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True); base.save(destination, "PNG")
