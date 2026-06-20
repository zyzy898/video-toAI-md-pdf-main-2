"""Tests for UploadSessionService (extracted to services/upload_session.py).

Includes regression coverage for the security fix: sensitive fields
(model API key) must never be written to the on-disk session JSON.
"""

import json
import logging

import pytest

from services.upload_session import UploadSessionService


def _make_service(tmp_path, max_memory=1024 * 1024):
    root = tmp_path / "sessions"
    root.mkdir()
    return UploadSessionService(
        session_root=root,
        memory_buffers={},
        memory_reserved_bytes={},
        max_memory_total_bytes=max_memory,
        logger_obj=logging.getLogger("test.upload"),
    )


class TestNormalizeUploadId:
    def test_sanitizes(self, tmp_path):
        svc = _make_service(tmp_path)
        assert "/" not in svc.normalize_upload_id("a/b")

    def test_rejects_too_long(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError):
            svc.normalize_upload_id("x" * 200)

    def test_empty_returns_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.normalize_upload_id("") == ""


class TestSecretNeverOnDisk:
    def test_api_key_not_persisted(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save("u1", {"filename": "v.mp4", "risk_api_key": "super-secret-key"})
        # raw JSON on disk must not contain the secret
        raw = (svc.session_root / "u1.json").read_text(encoding="utf-8")
        assert "super-secret-key" not in raw
        parsed = json.loads(raw)
        assert parsed["risk_api_key"] == ""

    def test_load_restores_secret_from_memory(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save("u1", {"filename": "v.mp4", "risk_api_key": "k"})
        loaded = svc.load("u1")
        assert loaded["risk_api_key"] == "k"

    def test_secret_lost_after_simulated_restart(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save("u1", {"filename": "v.mp4", "risk_api_key": "k"})
        # New instance == process restart: in-memory secrets are gone.
        svc2 = UploadSessionService(
            session_root=svc.session_root,
            memory_buffers={},
            memory_reserved_bytes={},
            max_memory_total_bytes=1024 * 1024,
            logger_obj=logging.getLogger("test.upload2"),
        )
        loaded = svc2.load("u1")
        assert loaded["risk_api_key"] == ""

    def test_delete_clears_secret(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save("u1", {"filename": "v.mp4", "risk_api_key": "k"})
        svc.delete("u1")
        assert "u1" not in svc._session_secrets
        assert not (svc.session_root / "u1.json").exists()


class TestMemoryReservation:
    def test_reserve_and_release(self, tmp_path):
        svc = _make_service(tmp_path, max_memory=1000)
        assert svc.reserve_memory("u1", 500) is True
        assert svc.reserved_total_bytes == 500
        svc.release_memory("u1")
        assert svc.reserved_total_bytes == 0

    def test_reserve_rejects_over_budget(self, tmp_path):
        svc = _make_service(tmp_path, max_memory=1000)
        assert svc.reserve_memory("u1", 800) is True
        assert svc.reserve_memory("u2", 800) is False  # would exceed budget

    def test_reserve_zero_rejected(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.reserve_memory("u1", 0) is False


class TestChunkHelpers:
    def test_normalize_received_chunks_dedupes_sorts(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.normalize_received_chunks([2, 0, 2, 1], 3) == [0, 1, 2]

    def test_normalize_received_chunks_filters_out_of_range(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.normalize_received_chunks([0, 5, -1], 3) == [0]

    def test_storage_mode_defaults_to_disk(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_chunk_storage_mode({}) == "disk"
        assert svc.get_chunk_storage_mode({"storage_mode": "memory"}) == "memory"
