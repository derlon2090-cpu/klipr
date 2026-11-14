"""Best-effort, DMCA-safe vocal-only audio rendering for exported media."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_command(source: Path, destination: Path) -> list[str]:
    """Build the FFmpeg command that gives Demucs a stable WAV input."""
    return [
        "ffmpeg", "-y", "-i", str(source), "-map", "0:a:0", "-vn",
        "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(destination),
    ]


def separate_command(audio: Path, stem_root: Path) -> list[str]:
    """Build a CPU-only two-stem Demucs invocation (vocals + accompaniment)."""
    return [
        "demucs", "--two-stems", "vocals", "-n", "htdemucs", "--device", "cpu",
        "-o", str(stem_root), str(audio),
    ]


def remux_command(source: Path, vocals: Path, destination: Path) -> list[str]:
    """Keep the original video bit-for-bit and replace only its audio track."""
    return [
        "ffmpeg", "-y", "-i", str(source), "-i", str(vocals),
        "-map", "0:v?", "-map", "1:a:0", "-map_metadata", "0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(destination),
    ]


def clean_vocal_audio(source: Path, destination: Path, scratch: Path, timeout_seconds: int = 900) -> bool:
    """Create a vocal-only MP4, returning False while leaving the source usable on failure.

    The worker treats separation as an enhancement: a damaged or unsupported audio
    track must never cause an otherwise valid VOD or Short export to fail.
    """
    scratch = scratch.resolve()
    audio = scratch / "source.wav"
    stem_root = scratch / "stems"
    vocals = stem_root / "htdemucs" / audio.stem / "vocals.wav"
    try:
        scratch.mkdir(parents=True, exist_ok=True)
        subprocess.run(extract_command(source, audio), check=True, shell=False, timeout=timeout_seconds)
        subprocess.run(separate_command(audio, stem_root), check=True, shell=False, timeout=timeout_seconds)
        if not vocals.is_file():
            raise FileNotFoundError(f"Demucs did not produce a vocal stem: {vocals}")
        subprocess.run(remux_command(source, vocals, destination), check=True, shell=False, timeout=timeout_seconds)
        return True
    except (OSError, subprocess.SubprocessError, FileNotFoundError) as error:
        destination.unlink(missing_ok=True)
        logger.warning("Audio separation failed for %s; preserving original audio: %s", source, error)
        return False
    finally:
        # Demucs stems and extracted PCM can be very large; never retain them.
        shutil.rmtree(scratch, ignore_errors=True)
