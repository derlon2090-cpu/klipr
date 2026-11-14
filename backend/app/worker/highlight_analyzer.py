"""Resource-bounded multi-stage highlight analysis for multi-hour VOD audio."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

from app.config import get_settings


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Candidate:
    start: float
    end: float
    peak_time: float
    energy: float
    z_score: float


@dataclass(frozen=True)
class Highlight:
    start: float
    end: float
    viral_score: int
    hook_title: str
    reason: str
    words: tuple[Word, ...]


def rms_series(wav_path: Path, bucket_seconds: int = 1) -> tuple[list[float], float]:
    """Read one small PCM bucket at a time instead of loading a multi-hour WAV."""
    values: list[float] = []
    with wave.open(str(wav_path), "rb") as reader:
        rate, frames = reader.getframerate(), reader.getnframes()
        bucket_frames = max(1, rate * bucket_seconds)
        while True:
            raw = reader.readframes(bucket_frames)
            if not raw: break
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            values.append(float(np.sqrt(np.mean(samples * samples))) / 32768.0 if len(samples) else 0.0)
    return values, frames / rate


def detect_peak_windows(wav_path: Path, target_seconds: int = 45, candidate_count: int = 30) -> tuple[list[Candidate], float]:
    target_seconds = max(10, min(180, target_seconds))
    energy, duration = rms_series(wav_path)
    if not energy: return [], duration
    array = np.asarray(energy, dtype=np.float32)
    baseline = float(np.median(array))
    deviation = float(np.median(np.abs(array - baseline))) * 1.4826 or float(np.std(array)) or 1e-6
    z_scores = (array - baseline) / deviation
    deltas = np.maximum(0.0, np.diff(array, prepend=array[0])) / deviation
    excitement = z_scores + 0.45 * deltas
    chosen: list[Candidate] = []
    for index in np.argsort(excitement)[::-1]:
        peak = float(index) + 0.5
        start = max(0.0, min(peak - target_seconds / 2, max(0.0, duration - target_seconds)))
        end = min(duration, start + target_seconds)
        if any(not (end <= item.start or start >= item.end) for item in chosen): continue
        chosen.append(Candidate(start, end, peak, float(array[index]), float(max(0.0, z_scores[index]))))
        if len(chosen) >= candidate_count: break
    return chosen, duration


def snap_sentence_boundaries(candidate: Candidate, words: list[Word], duration: float, target_seconds: int) -> tuple[float, float]:
    target_seconds = max(10, min(180, target_seconds))
    relevant = [word for word in words if word.start < candidate.end and word.end > candidate.start]
    if not relevant: return candidate.start, candidate.end
    start = max(candidate.start, relevant[0].start - 2.0)
    end = min(candidate.end, relevant[-1].end + 2.0)
    if end - start < 10:
        center = min(max(candidate.peak_time, 5), max(5, duration - 5))
        start, end = max(0.0, center - 5), min(duration, center + 5)
    if end - start > target_seconds:
        center = min(max(candidate.peak_time, target_seconds / 2), max(target_seconds / 2, duration - target_seconds / 2))
        start, end = max(0.0, center - target_seconds / 2), min(duration, center + target_seconds / 2)
    return start, end


def fallback_score(candidate: Candidate, words: list[Word]) -> tuple[int, str, str]:
    text = " ".join(word.text for word in words).strip()
    lower = text.lower()
    hype_terms = ("wow", "no way", "let's go", "clutch", "ضحك", "هههه", "مستحيل", "يا ساتر", "كفو", "كلتش")
    funny = any(term in lower for term in ("هههه", "ضحك", "lol", "lmao", "funny"))
    keyword_hits = sum(term in lower for term in hype_terms)
    density = min(1.0, len(words) / max(candidate.end - candidate.start, 1) / 2.5)
    completeness = 1.0 if text.endswith((".", "!", "?", "؟")) else 0.4
    score = int(round(min(100, 35 + min(candidate.z_score, 4.0) * 10 + keyword_hits * 7 + density * 10 + completeness * 5)))
    arabic = bool(re.search(r"[\u0600-\u06ff]", text))
    excerpt = " ".join(text.split()[:9]) or ("لحظة قوية" if arabic else "A huge stream moment")
    hook = ("لن تصدق ما حدث: " if arabic else "You won't believe this: ") + excerpt
    reason = "ردة فعل مضحكة" if funny else "لقطة كلتش حماسية" if candidate.z_score >= 2 else "تفاعل قوي ومتكامل"
    return max(0, min(100, score)), hook[:160], reason


def _ollama_score(candidate: Candidate, words: list[Word], fallback: tuple[int, str, str]) -> tuple[int, str, str]:
    settings = get_settings()
    if not settings.ollama_url: return fallback
    transcript = " ".join(word.text for word in words)[:4000]
    prompt = f"""Rate this Twitch/Kick moment for short-form virality. Return JSON only with keys score (0-100), hook_title (Arabic or English matching transcript), reason. Energy z-score: {candidate.z_score:.2f}. Transcript: {transcript}"""
    request = Request(settings.ollama_url.rstrip("/") + "/api/generate", data=json.dumps({"model":settings.ollama_model,"prompt":prompt,"stream":False}).encode(), headers={"Content-Type":"application/json","User-Agent":"Klipr Worker/1.0"}, method="POST")
    try:
        with urlopen(request, timeout=15) as response: raw = json.loads(response.read(1_000_000)).get("response", "")
        match = re.search(r"\{.*\}", raw, re.S)
        result = json.loads(match.group(0) if match else raw)
        llm_score = max(0, min(100, int(result["score"])))
        score = round(fallback[0] * 0.55 + llm_score * 0.45)
        return score, str(result.get("hook_title") or fallback[1])[:160], str(result.get("reason") or fallback[2])[:120]
    except Exception:
        return fallback


def transcribe_candidates(wav_path: Path, candidates: list[Candidate], scratch: Path) -> dict[int, list[Word]]:
    from faster_whisper import WhisperModel
    settings = get_settings()
    model = WhisperModel(settings.whisper_model, device=settings.whisper_device, compute_type=settings.whisper_compute_type)
    results: dict[int, list[Word]] = {}
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        for index, candidate in enumerate(candidates):
            segment_path = scratch / f"candidate-{index}.wav"
            subprocess.run(["ffmpeg","-y","-ss",f"{candidate.start:.3f}","-t",f"{candidate.end-candidate.start:.3f}","-i",str(wav_path),"-ac","1","-ar","16000",str(segment_path)], check=True, capture_output=True, shell=False)
            segments, _ = model.transcribe(str(segment_path), word_timestamps=True, vad_filter=True)
            results[index] = [Word(candidate.start + word.start, candidate.start + word.end, word.word.strip()) for segment in segments for word in (segment.words or [])]
        return results
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def analyze_highlights(wav_path: Path, scratch: Path, target_seconds: int = 45, max_clips: int = 3) -> list[Highlight]:
    candidates, duration = detect_peak_windows(wav_path, target_seconds, min(40, max(25, max_clips * 8)))
    transcriptions = transcribe_candidates(wav_path, candidates, scratch)
    ranked: list[Highlight] = []
    for index, candidate in enumerate(candidates):
        words = transcriptions.get(index, [])
        start, end = snap_sentence_boundaries(candidate, words, duration, target_seconds)
        relevant = tuple(word for word in words if word.start < end and word.end > start)
        score, hook, reason = _ollama_score(candidate, list(relevant), fallback_score(candidate, list(relevant)))
        ranked.append(Highlight(start, end, score, hook, reason, relevant))
    return sorted(ranked, key=lambda item: item.viral_score, reverse=True)[:max_clips]
