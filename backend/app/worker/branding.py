"""The non-configurable, zero-click brand treatment used for every exported Short."""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .thumbnails import _font


INTRO_SECONDS = 8
OUTRO_SECONDS = 2
REFERENCE_ART = Path(__file__).resolve().parents[1] / "assets" / "klipr-sponsor-intro.jpg"


CONCAT_FILTER = (
    "[0:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p[v0];"
    "[1:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p[v1];"
    "[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
    "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
    "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
)


def render_sponsor_intro(destination: Path, channel: str = "Klipr Stream Archive") -> None:
    """Render the supplied Klipr artwork into an eight-second, portrait sponsor bumper."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = Image.open(REFERENCE_ART).convert("RGB") if REFERENCE_ART.exists() else Image.new("RGB", (1280, 720), "#03120e")
    canvas = Image.new("RGB", (1080, 1920), "#03120e")
    # A blurred full-frame treatment preserves the supplied reference without cropping its focal art.
    background = source.resize((1080, 1920)).filter(ImageFilter.GaussianBlur(18))
    canvas.paste(background)
    shade = Image.new("RGBA", canvas.size, (0, 10, 8, 165))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade)
    art = source.copy()
    art.thumbnail((980, 552), Image.Resampling.LANCZOS)
    x, y = (1080 - art.width) // 2, 380
    canvas.alpha_composite(art.convert("RGBA"), (x, y))

    draw = ImageDraw.Draw(canvas)
    green, white = "#21e89b", "#ffffff"
    draw.rounded_rectangle((90, 1030, 990, 1250), radius=38, fill=(3, 18, 14, 230), outline=green, width=4)
    draw.text((540, 1080), channel, anchor="ma", font=_font(43), fill=white)
    draw.text((540, 1150), "STREAM HIGHLIGHTS", anchor="ma", font=_font(25), fill=green)
    draw.text((540, 1360), "بدعم من", anchor="ma", font=_font(34), fill=white)
    for label, x0, x1 in (("Advanced-pro.com", 100, 525), ("Boos5.1", 555, 980)):
        draw.rounded_rectangle((x0, 1440, x1, 1560), radius=28, fill=(3, 18, 14, 235), outline=green, width=3)
        draw.text(((x0 + x1) // 2, 1500), label, anchor="mm", font=_font(29), fill=white)
    draw.text((540, 1695), "WATCH • CLIP • SHARE", anchor="ma", font=_font(24), fill=green)
    still = destination.with_suffix(".png")
    canvas.convert("RGB").save(still)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(still), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(INTRO_SECONDS), "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(destination),
    ], check=True, shell=False)


def prepend_intro(intro: Path, clip: Path, destination: Path) -> None:
    """Join the bumper and vertical clip while normalising both audio streams."""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(intro), "-i", str(clip), "-filter_complex",
        CONCAT_FILTER, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(destination),
    ], check=True, shell=False)


def render_short_outro(destination: Path, channel: str = "Klipr Stream Archive") -> None:
    """Render a concise portrait end card for every exported Short."""
    canvas = Image.new("RGB", (1080, 1920), "#03120e")
    draw = ImageDraw.Draw(canvas)
    green, white = "#21e89b", "#ffffff"
    draw.rounded_rectangle((105, 610, 975, 1285), radius=64, fill="#071f18", outline=green, width=6)
    draw.text((540, 760), "KLIPR.CLOUD", anchor="mm", font=_font(66), fill=green)
    draw.text((540, 920), channel[:48], anchor="mm", font=_font(44), fill=white)
    draw.text((540, 1070), "تابع • شارك • اشترك", anchor="mm", font=_font(38), fill=white)
    draw.text((540, 1190), "FOLLOW • SHARE • SUBSCRIBE", anchor="mm", font=_font(25), fill=green)
    still = destination.with_suffix(".png")
    canvas.save(still)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(still), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(OUTRO_SECONDS), "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(destination),
    ], check=True, shell=False)
    still.unlink(missing_ok=True)


def append_outro(clip: Path, outro: Path, destination: Path) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-i", str(clip), "-i", str(outro), "-filter_complex",
        CONCAT_FILTER, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", str(destination),
    ], check=True, shell=False)
