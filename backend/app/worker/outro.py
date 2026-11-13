"""YouTube end-screen compositor; all FFmpeg execution stays argument-list based."""
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw
from .thumbnails import _font, platform_color
SAFE_ZONES = ((110, 310, 560, 315), (1250, 310, 560, 315))
def recommendation_slots(vods: list[object]) -> list[object | None]: return (vods[:2] + [None, None])[:2]
def render_outro(destination: Path, platform: str, channel: str, tagline: str, metadata: str, recommendations: list[object]) -> None:
    accent = platform_color(platform); image = Image.new("RGB", (1920,1080), "#0b0b10"); draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35,35,1885,1045), 40, outline=accent, width=14)
    for index, (x,y,w,h) in enumerate(SAFE_ZONES):
        draw.rounded_rectangle((x,y,x+w,y+h), 28, fill="#15151c", outline=accent, width=7)
        draw.text((x+150,y+135), "Watch Next" if recommendation_slots(recommendations)[index] else "More soon", font=_font(30), fill="white")
    draw.ellipse((840,90,1080,330), fill="#17171d", outline=accent, width=10); draw.text((760,365), channel or "Klipr Archive", font=_font(44), fill="white")
    draw.rounded_rectangle((790,430,1130,500), 28, fill=accent); draw.text((840,447), "Subscribe / اشترك", font=_font(25), fill="black")
    draw.rectangle((0,950,1920,1080), fill="#101016"); draw.text((65,995), f"{metadata}  •  {tagline}", font=_font(26), fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True); image.save(destination.with_suffix(".png"))
    subprocess.run(["ffmpeg","-y","-loop","1","-i",str(destination.with_suffix('.png')),"-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t","15","-r","30","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(destination)], check=True, shell=False)
def concat_command(master: Path, outro: Path, destination: Path) -> list[str]:
    return ["ffmpeg","-y","-i",str(master),"-i",str(outro),"-filter_complex","[0:v]scale=1920:1080,setsar=1[v0];[1:v]scale=1920:1080,setsar=1[v1];[0:a]aresample=48000[a0];[1:a]aresample=48000[a1];[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]","-map","[v]","-map","[a]","-c:v","libx264","-c:a","aac",str(destination)]
