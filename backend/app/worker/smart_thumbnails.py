"""Background VOD frame selection and Arabic thumbnail rendering."""
import base64
import json
import subprocess
from pathlib import Path
from uuid import UUID

import requests
from arabic_reshaper import reshape
from bidi.algorithm import get_display
from celery import shared_task
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from app.config import get_settings
from app.db import SessionLocal
from app.models import SmartThumbnail, Vod
from app.storage import download_file
from app.worker.tasks import WORK_ROOT


def _update(item_id: UUID, **values: object) -> None:
    with SessionLocal() as db:
        item = db.get(SmartThumbnail, item_id)
        if item:
            for key, value in values.items(): setattr(item, key, value)
            db.commit()


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"):
        if Path(path).exists(): return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _hook(context: str, index: int) -> str:
    settings = get_settings()
    fallback = ["لحظة قلبت البث", "مستحيل اللي صار", "ردة فعل نارية"][index % 3]
    if not settings.deepseek_api_key:
        return fallback
    prompt = f"اكتب عنواناً عربياً جذاباً من 3 إلى 5 كلمات فقط يصف هذا الحدث فعلاً، بلا هاشتاقات أو علامات اقتباس: {context[:700]}"
    try:
        response = requests.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"}, json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.75, "max_tokens": 32}, timeout=25)
        response.raise_for_status()
        title = response.json()["choices"][0]["message"]["content"].strip().replace("\n", " ").strip('"“”')
        return title[:80] or fallback
    except Exception:
        return fallback


def _vision_context(frame: Path, fallback: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback
    try:
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": [{"type": "text", "text": "Describe the visible exciting moment in this livestream frame in one short Arabic sentence. Do not invent facts."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}}]}], "max_tokens": 80}
        response = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}, json=payload, timeout=35)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()[:500] or fallback
    except Exception:
        return fallback


def _crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    source_ratio, target_ratio = image.width / image.height, size[0] / size[1]
    if source_ratio > target_ratio:
        width = int(image.height * target_ratio); left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    else:
        height = int(image.width / target_ratio); top = max(0, (image.height - height) // 3)
        image = image.crop((0, top, image.width, top + height))
    return image.resize(size, Image.Resampling.LANCZOS)


def _render(frame: Path, output: Path, headline: str, platform: str, style: str) -> None:
    portrait = platform in {"tiktok", "shorts", "reels"}
    size = (1080, 1920) if portrait else ((1920, 1080) if platform in {"x", "kick"} else (1280, 720))
    image = _crop(Image.open(frame).convert("RGB"), size)
    image = ImageEnhance.Contrast(image).enhance(1.18)
    image = ImageEnhance.Color(image).enhance(1.15)
    draw = ImageDraw.Draw(image)
    accent = "#53fc18" if platform == "kick" else "#ff1744" if platform in {"tiktok", "shorts", "reels"} else "#ff003c"
    if style != "none":
        width = 18 if style == "bold" else 8
        draw.rectangle((width // 2, width // 2, size[0] - width // 2, size[1] - width // 2), outline=accent, width=width)
    text = get_display(reshape(headline))
    font = _font(82 if portrait else 58)
    box = draw.multiline_textbbox((0, 0), text, font=font, stroke_width=3)
    x = (size[0] - (box[2] - box[0])) // 2
    y = int(size[1] * (0.67 if portrait else 0.72))
    draw.rounded_rectangle((max(24, x - 34), y - 24, min(size[0] - 24, x + box[2] + 34), y + box[3] + 28), radius=24, fill="#050505d9")
    draw.multiline_text((x, y), text, font=font, fill="white", stroke_width=4, stroke_fill="black", align="center")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=95, optimize=True)


@shared_task(bind=True)
def generate_smart_thumbnails(self, ids: list[str]) -> None:
    item_ids = [UUID(value) for value in ids]
    with SessionLocal() as db:
        items = [db.get(SmartThumbnail, item_id) for item_id in item_ids]
        items = [item for item in items if item]
        vod = db.get(Vod, items[0].vod_id) if items else None
        if not vod or not vod.storage_key:
            for item in items: _update(item.id, status="failed", error_message="The selected VOD is unavailable.")
            return
        duration = max(1, vod.duration_seconds or 1)
    job_dir = WORK_ROOT / "smart-thumbnails" / str(items[0].vod_id)
    source = job_dir / "vod.mp4"
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        download_file(vod.storage_key, source)
        for index, item in enumerate(items):
            _update(item.id, status="processing", progress=15, error_message=None)
            timestamp = max(1.0, min(float(duration - 1), duration * (0.22 + index * 0.29)))
            frame = job_dir / f"frame-{item.id}.jpg"
            subprocess.run(["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(source), "-frames:v", "1", "-q:v", "2", str(frame)], check=True, capture_output=True, text=True, timeout=180)
            context = _vision_context(frame, f"لحظة بارزة من البث عند الدقيقة {int(timestamp // 60) + 1}")
            _update(item.id, progress=55, timestamp_seconds=timestamp, context=context)
            headline = _hook(context, index)
            output = job_dir / f"thumbnail-{item.id}.jpg"
            _render(frame, output, headline, item.platform, item.frame_style)
            _update(item.id, status="ready", progress=100, headline=headline, output_path=str(output))
    except Exception as error:
        for item in items:
            _update(item.id, status="failed", error_message=str(error)[-1000:])
        raise


