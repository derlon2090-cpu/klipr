from pathlib import Path
from unittest.mock import patch

from app.worker.audio_clean import clean_vocal_audio, extract_command, remux_command


def test_ffmpeg_commands_are_argument_lists(tmp_path):
    source, wav, output = tmp_path / "vod.mp4", tmp_path / "audio.wav", tmp_path / "clean.mp4"
    extract = extract_command(source, wav)
    remux = remux_command(source, wav, output)
    assert extract[:2] == ["ffmpeg", "-y"]
    assert "-vn" in extract and "-c:a" in extract
    assert remux[remux.index("-c:v") + 1] == "copy"
    assert remux[remux.index("-b:a") + 1] == "192k"


def test_failure_preserves_original_and_removes_stems(tmp_path):
    source, output, scratch = tmp_path / "vod.mp4", tmp_path / "clean.mp4", tmp_path / "scratch"
    source.write_bytes(b"original")
    with patch("app.worker.audio_clean.subprocess.run", side_effect=OSError("ffmpeg unavailable")) as run:
        assert clean_vocal_audio(source, output, scratch, timeout_seconds=1) is False
    assert source.read_bytes() == b"original"
    assert not output.exists() and not scratch.exists()
    assert run.call_args.kwargs["shell"] is False
