"""Tests for video content magic-byte validation (services/media_validation.py)."""

import pytest

from services.media_validation import _looks_like_video_container, is_valid_video_content


class TestSignatureMatching:
    def test_mp4_ftyp(self):
        assert _looks_like_video_container(b"\x00\x00\x00\x20ftypisom\x00\x00")

    def test_webm_ebml(self):
        assert _looks_like_video_container(b"\x1a\x45\xdf\xa3" + b"\x00" * 8)

    def test_avi_riff(self):
        assert _looks_like_video_container(b"RIFF\x00\x00\x00\x00AVI \x00\x00")

    def test_flv(self):
        assert _looks_like_video_container(b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00")

    def test_ogg(self):
        assert _looks_like_video_container(b"OggS\x00\x02\x00\x00\x00\x00\x00\x00")


class TestRejection:
    def test_plain_text(self):
        assert not _looks_like_video_container(b"hello this is plain text!!")

    def test_html(self):
        assert not _looks_like_video_container(b"<!DOCTYPE html><html><head>")

    def test_too_short(self):
        assert not _looks_like_video_container(b"abc")

    def test_empty(self):
        assert not _looks_like_video_container(b"")


class TestIsValidVideoContent:
    def test_valid_mp4_file(self, tmp_path):
        p = tmp_path / "v.mp4"
        p.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32)
        assert is_valid_video_content(p) is True

    def test_disguised_text_file(self, tmp_path):
        # extension says mp4, content is text -> rejected
        p = tmp_path / "fake.mp4"
        p.write_bytes(b"this is not a video at all, just text content")
        assert is_valid_video_content(p) is False

    def test_missing_file(self, tmp_path):
        assert is_valid_video_content(tmp_path / "nope.mp4") is False

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.mp4"
        p.write_bytes(b"")
        assert is_valid_video_content(p) is False
