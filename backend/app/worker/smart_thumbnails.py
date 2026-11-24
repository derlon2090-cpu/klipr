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
from app.models import Clip, SmartThumbnail, Stream, Vod
from app.storage import presigned_download_url
from app.worker.tasks import WORK_ROOT


def _update(item_id: UUID, **values: object) -> None:
    with SessionLocal() as db:
        item = db.get(SmartThumbnail, item_id)
        if item:
            for key, value in values.items(): setattr(item, key, value)
            db.commit()


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Noto Naskh has complete Arabic shaping and punctuation support; DejaVu
    # remains only a last-resort fallback for non-Arabic worker images.
    for path in ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(path).exists(): return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _hook(context: str, index: int) -> str:
    settings = get_settings()
    fallback = ["لحظة صادمة", "موقف غريب", "ردة فعل"][index % 3]
    if not settings.deepseek_api_key:
        return fallback
    prompt = f"اكتب عبارة عربية قصيرة جداً من كلمتين أو ثلاث فقط للثامبنيل، مثيرة لكنها صادقة، وتلخص أقوى ما حدث. لا هاشتاقات ولا علامات اقتباس ولا شرح: {context[:700]}"
    try:
        response = requests.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"}, json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.75, "max_tokens": 32}, timeout=25)
        response.raise_for_status()
        title = response.json()["choices"][0]["message"]["content"].strip().replace("\n", " ").strip('"“”')
        words = title.split()
        candidate = " ".join(words[:3])[:44]
        # Keep the image headline trustworthy and readable. If the model
        # produces mixed-script/noisy text, use a concise approved Arabic hook.
        return candidate if candidate and all("\u0600" <= char <= "\u06ff" or char.isspace() for char in candidate) else fallback
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
    source = Image.open(frame).convert("RGB")
    # Keep horizontal covers at the actual source frame dimensions. Upscaling
    # a 1080p broadcast to a fake 4K JPEG adds neither detail nor quality.
    size = (1080, 1920) if portrait else source.size
    image = _crop(source, size)
    image = ImageEnhance.Contrast(image).enhance(1.18)
    image = ImageEnhance.Color(image).enhance(1.15)
    draw = ImageDraw.Draw(image)
    accent = "#53fc18" if platform == "kick" else "#ff1744" if platform in {"tiktok", "shorts", "reels"} else "#ff003c"
    if style != "none":
        border = max(8, round(size[0] * (.014 if style == "bold" else .008)))
        # One uninterrupted frame, drawn inside the image boundary so no
        # segment disappears when platforms crop the thumbnail preview.
        radius = max(18, round(size[0] * .035))
        draw.rounded_rectangle((border // 2, border // 2, size[0] - 1 - border // 2, size[1] - 1 - border // 2), radius=radius, outline=accent, width=border)
    # Use a compact, readable Arabic headline in a dedicated contrast panel.
    words = headline.split()
    lines = [" ".join(words[:max(1, len(words) // 2)]), " ".join(words[max(1, len(words) // 2):])]
    lines = [line for line in lines if line] or [headline]
    font_size = max(58, round(size[0] * (.105 if portrait else .065)))
    font = _font(font_size)
    margin = int(size[0] * .055)
    line_gap = int(font_size * .92)
    for line_index, line in enumerate(lines):
        color = "#ffffff" if line_index == 0 else "#ffe600"
        # Pillow was built with libraqm in the worker, so pass logical Arabic
        # text directly and let its RTL shaping engine join glyphs correctly.
        draw.text((size[0] - margin, margin + line_index * line_gap), line, anchor="ra", direction="rtl", language="ar", font=font, fill=color, stroke_width=max(3, font_size // 16), stroke_fill="#080808")
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
        streams = db.query(Stream).filter(Stream.source_url == vod.source_url).all()
        stream_ids = [stream.id for stream in streams]
        highlights = db.query(Clip).filter(Clip.stream_id.in_(stream_ids)).order_by(Clip.viral_score.desc(), Clip.score.desc()).limit(3).all() if stream_ids else []
    job_dir = WORK_ROOT / "smart-thumbnails" / str(items[0].vod_id)
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        # FFmpeg seeks through the signed R2 URL with HTTP range requests, so
        # three thumbnails do not first download a 50GB VOD to the worker.
        source_url = presigned_download_url(vod.storage_key)
        for index, item in enumerate(items):
            _update(item.id, status="processing", progress=15, error_message=None)
            timestamp = max(1.0, min(float(duration - 1), (highlights[index].start_seconds + highlights[index].end_seconds) / 2 if index < len(highlights) else duration * (0.22 + index * 0.29)))
            frame = job_dir / f"frame-{item.id}.jpg"
            subprocess.run(["ffmpeg", "-y", "-ss", str(timestamp), "-i", source_url, "-frames:v", "1", "-q:v", "2", str(frame)], check=True, capture_output=True, text=True, timeout=180)
            fallback_context = (highlights[index].hook_title or highlights[index].highlight_reason) if index < len(highlights) else f"لحظة بارزة من البث عند الدقيقة {int(timestamp // 60) + 1}"
            context = _vision_context(frame, fallback_context)
            _update(item.id, progress=55, timestamp_seconds=timestamp, context=context)
            headline = _hook(context, index)
            output = job_dir / f"thumbnail-{item.id}.jpg"
            _render(frame, output, headline, item.platform, item.frame_style)
            _update(item.id, status="ready", progress=100, headline=headline, output_path=str(output))
    except Exception as error:
        for item in items:
            _update(item.id, status="failed", error_message=str(error)[-1000:])
        raise


