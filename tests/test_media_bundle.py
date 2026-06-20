"""Tests for subtitle parsing/rendering helpers (services/media_bundle.py).

Covers the pure timestamp + SRT/VTT/TXT functions. File-discovery and bundle
assembly touch the OUTPUT_ROOT filesystem and are out of scope here.
"""

import pytest

from services.media_bundle import (
    _format_seconds_to_mmss,
    _format_seconds_to_vtt_timestamp,
    _parse_srt_file_entries,
    _parse_srt_timestamp_to_seconds,
    _render_txt_from_entries,
    _render_vtt_from_entries,
)


class TestFormatMmss:
    def test_basic(self):
        assert _format_seconds_to_mmss(90) == "01:30"

    def test_zero(self):
        assert _format_seconds_to_mmss(0) == "00:00"

    def test_negative_clamped(self):
        assert _format_seconds_to_mmss(-5) == "00:00"


class TestFormatVttTimestamp:
    def test_basic(self):
        assert _format_seconds_to_vtt_timestamp(3661.5) == "01:01:01.500"

    def test_millisecond_rounding_carry(self):
        # 0.9995s -> rounds to 1000ms -> carries to whole second
        assert _format_seconds_to_vtt_timestamp(0.9999) == "00:00:01.000"


class TestParseSrtTimestamp:
    def test_comma_millis(self):
        assert _parse_srt_timestamp_to_seconds("00:01:30,500") == 90.5

    def test_dot_millis(self):
        assert _parse_srt_timestamp_to_seconds("01:00:00.250") == 3600.25

    def test_no_millis(self):
        assert _parse_srt_timestamp_to_seconds("00:00:05") == 5.0

    def test_invalid(self):
        assert _parse_srt_timestamp_to_seconds("nope") is None


SAMPLE_SRT = """1
00:00:00,000 --> 00:00:02,000
Hello world

2
00:00:02,500 --> 00:00:04,000
Second line
"""


class TestParseSrtFileEntries:
    def test_parses_two_entries(self, tmp_path):
        srt = tmp_path / "s.srt"
        srt.write_text(SAMPLE_SRT, encoding="utf-8")
        entries = _parse_srt_file_entries(srt)
        assert len(entries) == 2
        assert entries[0]["text"] == "Hello world"
        assert entries[0]["start_seconds"] == 0.0
        assert entries[1]["start_seconds"] == 2.5

    def test_missing_file_returns_empty(self, tmp_path):
        assert _parse_srt_file_entries(tmp_path / "nope.srt") == []


class TestRenderExports:
    def _entries(self):
        return [
            {"index": 1, "start_seconds": 0.0, "end_seconds": 2.0, "text": "Hello"},
            {"index": 2, "start_seconds": 2.5, "end_seconds": 4.0, "text": "World"},
        ]

    def test_vtt_has_header(self):
        out = _render_vtt_from_entries(self._entries())
        assert out.startswith("WEBVTT")
        assert "-->" in out

    def test_txt_has_timestamps_and_text(self):
        out = _render_txt_from_entries(self._entries())
        assert "[00:00] Hello" in out
        assert "[00:02] World" in out

    def test_txt_skips_empty_text(self):
        entries = [{"index": 1, "start_seconds": 0.0, "end_seconds": 1.0, "text": ""}]
        assert _render_txt_from_entries(entries) == ""
