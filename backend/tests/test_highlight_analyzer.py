import sys
import types
import wave

import numpy as np
import pytest

from app.worker.highlight_analyzer import Candidate, Word, detect_peak_windows, fallback_score, snap_sentence_boundaries, transcribe_candidates


def _write_wav(path, seconds=24, peak_second=12):
    rate = 16000
    samples = np.full(rate * seconds, 120, dtype=np.int16)
    samples[rate * peak_second:rate * (peak_second + 1)] = 28000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate); output.writeframes(samples.tobytes())


def test_audio_peak_scan_finds_excited_window(tmp_path):
    wav = tmp_path / "audio.wav"; _write_wav(wav)
    candidates, duration = detect_peak_windows(wav, target_seconds=10, candidate_count=3)
    assert duration == pytest.approx(24)
    assert candidates and candidates[0].start <= 12.5 <= candidates[0].end
    assert candidates[0].z_score > 1


def test_sentence_boundaries_respect_custom_duration():
    candidate = Candidate(0, 45, 22, .8, 3)
    words = [Word(3, 4, "بداية"), Word(20, 21, "كلتش"), Word(40, 41, "نهاية!")]
    start, end = snap_sentence_boundaries(candidate, words, duration=100, target_seconds=30)
    assert 10 <= end - start <= 30
    assert start <= candidate.peak_time <= end


def test_fallback_score_ranks_energy_and_generates_metadata():
    words = [Word(0, 1, "يا ساتر"), Word(1, 2, "كلتش!")]
    high = fallback_score(Candidate(0, 20, 10, .9, 4), words)
    low = fallback_score(Candidate(0, 20, 10, .1, 0), [])
    assert high[0] > low[0] and 0 <= high[0] <= 100
    assert high[1] and high[2]


def test_candidate_scratch_is_cleaned_when_transcription_fails(tmp_path, monkeypatch):
    class BrokenModel:
        def __init__(self, *args, **kwargs): pass
        def transcribe(self, *args, **kwargs): raise RuntimeError("offline")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=BrokenModel))
    monkeypatch.setattr("app.worker.highlight_analyzer.subprocess.run", lambda *args, **kwargs: None)
    scratch = tmp_path / "candidate-scratch"
    with pytest.raises(RuntimeError):
        transcribe_candidates(tmp_path / "audio.wav", [Candidate(0, 10, 5, .5, 2)], scratch)
    assert not scratch.exists()
