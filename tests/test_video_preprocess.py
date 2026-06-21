"""Tests for video preprocessing helpers (services/video_preprocess.py).

Covers the pure helpers and the early-return guard paths that do NOT invoke
ffmpeg (config-disabled, below-threshold). The actual transcode/concat paths
shell out to ffmpeg and are out of scope for unit tests.
"""

import importlib

import pytest

import services.video_preprocess as vp


class TestFormatFfmpegSeconds:
    def test_zero(self):
        assert vp._format_ffmpeg_seconds(0) == "0"

    def test_strips_trailing_zeros(self):
        assert vp._format_ffmpeg_seconds(1.5) == "1.5"
        assert vp._format_ffmpeg_seconds(2.0) == "2"

    def test_negative_clamped(self):
        assert vp._format_ffmpeg_seconds(-5) == "0"


class TestBuildConcatFile:
    def test_writes_escaped_entries(self, tmp_path):
        list_path = tmp_path / "concat_list.txt"
        a = tmp_path / "a.mp4"
        b = tmp_path / "b.mp4"
        a.touch()
        b.touch()
        vp._build_ffmpeg_concat_file(list_path, [a, b])
        content = list_path.read_text(encoding="utf-8")
        assert content.count("file '") == 2
        # forward slashes used even on Windows
        assert "\\" not in content


class _FakeAgent:
    def __init__(self, ffmpeg_cmd="ffmpeg"):
        self.ffmpeg_cmd = ffmpeg_cmd


class TestPrepareLongVideoGuards:
    def test_disabled_by_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vp, "LONG_VIDEO_PREPROCESS_ENABLED", False)
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        path, meta = vp._prepare_long_video_analysis_source(
            agent=_FakeAgent(), video_path=video, output_dir=out_dir
        )
        assert path == video
        assert meta["reason"] == "disabled_by_config"
        assert meta["used"] is False

    def test_below_threshold_skips(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vp, "LONG_VIDEO_PREPROCESS_ENABLED", True)
        monkeypatch.setattr(vp, "LONG_VIDEO_PREPROCESS_MIN_FILE_SIZE_MB", 10000)
        # short duration so duration threshold also not met
        monkeypatch.setattr(vp, "_probe_video_duration_seconds", lambda *a, **k: 5.0)
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        path, meta = vp._prepare_long_video_analysis_source(
            agent=_FakeAgent(), video_path=video, output_dir=out_dir
        )
        assert path == video
        assert meta["reason"] == "below_threshold"
        assert meta["used"] is False
