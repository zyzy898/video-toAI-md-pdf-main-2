"""Tests for optional ffmpeg audio pre-processing (asr.audio_preprocess)."""

from pathlib import Path

from asr.audio_preprocess import cleanup_temp_audio, preprocess_audio


def test_preprocess_missing_source_returns_input(tmp_path):
    missing = tmp_path / "nope.mp4"
    assert preprocess_audio(missing) == missing


def test_preprocess_failure_falls_back_to_source(tmp_path, monkeypatch):
    # A real file but ffmpeg "fails" -> we must return the original path and
    # leave no temp file behind.
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"not really a video")

    class _FakeResult:
        returncode = 1
        stderr = "boom"

    import asr.audio_preprocess as mod

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _FakeResult())

    out = preprocess_audio(src, ffmpeg_cmd="ffmpeg")
    assert out == src


def test_cleanup_only_removes_our_temp_files(tmp_path):
    # Never delete arbitrary files: only ones with our temp prefix.
    user_file = tmp_path / "important.wav"
    user_file.write_bytes(b"keep me")
    cleanup_temp_audio(user_file)
    assert user_file.exists()

    temp_file = tmp_path / "asr_clean_xyz.wav"
    temp_file.write_bytes(b"scratch")
    cleanup_temp_audio(temp_file)
    assert not temp_file.exists()


def test_cleanup_none_is_safe():
    cleanup_temp_audio(None)  # must not raise
