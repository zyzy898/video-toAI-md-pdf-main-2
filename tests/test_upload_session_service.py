"""Tests for UploadSessionService (extracted to services/upload_session.py).

Includes regression coverage for the security fix: sensitive fields
(model API key) must never be written to the on-disk session JSON.
"""

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock

import pytest

from services.upload_session import UploadSessionService, UploadVideoAutoCleanupService


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


def _completed_session(path: Path) -> dict:
    stat_result = path.stat()
    return {
        "status": "completed",
        "total_size": stat_result.st_size,
        "result": {"filepath": str(path), "filename": path.name},
        "result_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "result_destination_identity": {
            "device": int(stat_result.st_dev),
            "inode": int(stat_result.st_ino),
            "ctime_ns": int(stat_result.st_ctime_ns),
        },
    }


class TestNormalizeUploadId:
    def test_rejects_path_like_aliases(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError):
            svc.normalize_upload_id("a/b")

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
        assert svc.delete("u1") is True
        assert "u1" not in svc._session_secrets
        assert not (svc.session_root / "u1.json").exists()

    def test_delete_reports_unlink_failure(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path)
        svc.save("u1", {"filename": "v.mp4", "risk_api_key": "k"})
        svc.session_temp_path("u1").write_bytes(b"partial")
        session_path = svc.session_json_path("u1")
        real_unlink = Path.unlink

        def fail_session_unlink(path, *args, **kwargs):
            if path == session_path:
                raise PermissionError("simulated locked file")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_session_unlink)

        assert svc.delete("u1") is False
        assert session_path.exists()


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


class TestDestinationReservation:
    def test_same_name_is_reserved_atomically(self, tmp_path):
        svc = _make_service(tmp_path)
        upload_root = tmp_path / "uploads"
        upload_root.mkdir()

        with ThreadPoolExecutor(max_workers=8) as executor:
            paths = list(
                executor.map(
                    lambda _index: svc.reserve_unique_destination(
                        "clip.mp4", upload_root=upload_root
                    ),
                    range(8),
                )
            )

        assert len(set(paths)) == 8
        assert all(path.exists() for path in paths)
        assert {path.name for path in paths} == {
            "clip.mp4",
            "clip_1.mp4",
            "clip_2.mp4",
            "clip_3.mp4",
            "clip_4.mp4",
            "clip_5.mp4",
            "clip_6.mp4",
            "clip_7.mp4",
        }

    def test_preserves_extension_when_basename_is_non_ascii(self, tmp_path):
        svc = _make_service(tmp_path)
        upload_root = tmp_path / "uploads"

        path = svc.reserve_unique_destination("视频.mp4", upload_root=upload_root)

        assert path.name == "upload.mp4"
        assert path.suffix == ".mp4"

    def test_reservation_token_makes_destination_session_unique(self, tmp_path):
        svc = _make_service(tmp_path)
        upload_root = tmp_path / "uploads"

        first = svc.reserve_unique_destination(
            "clip.mp4",
            upload_root=upload_root,
            reservation_token="a" * 32,
        )
        second = svc.reserve_unique_destination(
            "clip.mp4",
            upload_root=upload_root,
            reservation_token="b" * 32,
        )

        assert first.name == f"clip_{'a' * 32}.mp4"
        assert second.name == f"clip_{'b' * 32}.mp4"
        assert first != second


class TestStaleSessionCleanup:
    def test_removes_stale_sessions_and_orphan_artifacts_but_keeps_fresh_upload(self, tmp_path):
        svc = _make_service(tmp_path)
        now = 10_000.0
        stale = now - 101

        svc.save("fresh", {"status": "uploading", "filename": "fresh.mp4"})
        fresh_part = svc.session_temp_path("fresh")
        fresh_part.write_bytes(b"fresh")

        svc.save("stale", {"status": "uploading", "filename": "stale.mp4"})
        stale_json = svc.session_json_path("stale")
        stale_part = svc.session_temp_path("stale")
        stale_part.write_bytes(b"stale")

        corrupt_json = svc.session_json_path("corrupt")
        corrupt_json.write_text("{not-json", encoding="utf-8")
        corrupt_part = svc.session_temp_path("corrupt")
        corrupt_part.write_bytes(b"corrupt")

        orphan_part = svc.session_temp_path("orphan")
        orphan_part.write_bytes(b"orphan")
        stale_tmp = svc.session_root / "interrupted.tmp"
        stale_tmp.write_bytes(b"tmp")

        for path in (stale_json, stale_part, corrupt_json, corrupt_part, orphan_part, stale_tmp):
            os.utime(path, (stale, stale))

        svc.cleanup_stale_sessions(
            upload_root=svc.session_root.parent,
            ttl_seconds=100,
            now=now,
        )

        assert svc.session_json_path("fresh").exists()
        assert fresh_part.exists()
        assert not stale_json.exists()
        assert not stale_part.exists()
        assert not corrupt_json.exists()
        assert not corrupt_part.exists()
        assert not orphan_part.exists()
        assert not stale_tmp.exists()

    def test_reconciles_completed_receipts_without_deleting_live_video(self, tmp_path):
        svc = _make_service(tmp_path)
        upload_root = svc.session_root.parent
        now = 20_000.0
        stale = now - 101

        live_video = upload_root / "live.mp4"
        live_video.write_bytes(b"live")
        svc.save("live-receipt", _completed_session(live_video))

        missing_video = upload_root / "missing.mp4"
        svc.save(
            "missing-receipt",
            {
                "status": "completed",
                "result": {"filepath": str(missing_video), "filename": missing_video.name},
            },
        )

        stale_video = upload_root / "still-loaded.mp4"
        stale_video.write_bytes(b"loaded")
        svc.save("stale-receipt", _completed_session(stale_video))
        os.utime(svc.session_json_path("stale-receipt"), (stale, stale))
        os.utime(stale_video, (now, now))

        svc.cleanup_stale_sessions(
            upload_root=upload_root,
            ttl_seconds=100,
            now=now,
        )

        assert svc.session_json_path("live-receipt").exists()
        assert not svc.session_json_path("missing-receipt").exists()
        assert not svc.session_json_path("stale-receipt").exists()
        assert live_video.exists()
        assert stale_video.exists()

    def test_reconciles_completed_receipt_without_ownership_metadata_as_expired(
        self, tmp_path
    ):
        svc = _make_service(tmp_path)
        upload_root = svc.session_root.parent
        legacy_video = upload_root / "legacy.mp4"
        legacy_video.write_bytes(b"legacy")
        svc.save(
            "legacy-receipt",
            {
                "status": "completed",
                "total_size": legacy_video.stat().st_size,
                "result": {
                    "filepath": str(legacy_video),
                    "filename": legacy_video.name,
                },
            },
        )

        svc.cleanup_stale_sessions(upload_root=upload_root, ttl_seconds=100)

        assert not svc.session_json_path("legacy-receipt").exists()
        assert legacy_video.exists()

    def test_pending_destination_paths_ignores_deleted_tombstone(self, tmp_path):
        svc = _make_service(tmp_path)
        upload_root = svc.session_root.parent
        pending_path = upload_root / "pending.mp4"
        svc.save(
            "cancelled-finalize",
            {
                "status": "finalizing",
                "pending_destination_deleted": True,
                "pending_result": {
                    "filepath": str(pending_path),
                    "filename": pending_path.name,
                },
            },
        )

        assert svc.pending_destination_paths(upload_root=upload_root) == set()

    def test_video_cleanup_invokes_session_reconciliation(self, tmp_path):
        calls = []
        cleanup = UploadVideoAutoCleanupService(
            upload_root=tmp_path / "uploads",
            allowed_extensions={"mp4"},
            ttl_seconds=60,
            scan_interval_seconds=60,
            logger_obj=logging.getLogger("test.upload.cleanup"),
            session_cleanup=lambda: calls.append("sessions") or 0,
        )

        assert cleanup.cleanup_once() == 0
        assert calls == ["sessions"]

    def test_video_cleanup_uses_operation_lock_and_preserves_pending_paths(
        self, tmp_path, monkeypatch
    ):
        upload_root = tmp_path / "uploads"
        upload_root.mkdir()
        pending_path = upload_root / "pending.mp4"
        stale_path = upload_root / "stale.mp4"
        pending_path.write_bytes(b"pending")
        stale_path.write_bytes(b"stale")
        old = 1.0
        os.utime(pending_path, (old, old))
        os.utime(stale_path, (old, old))
        operation_lock = RLock()
        observed = []
        real_unlink = Path.unlink

        def locked_unlink(path, *args, **kwargs):
            observed.append(("unlink", operation_lock._is_owned(), path.name))
            return real_unlink(path, *args, **kwargs)

        def session_cleanup():
            observed.append(("sessions", operation_lock._is_owned(), ""))
            return 0

        def protected_paths():
            observed.append(("protected", operation_lock._is_owned(), ""))
            return {pending_path}

        monkeypatch.setattr(Path, "unlink", locked_unlink)
        cleanup = UploadVideoAutoCleanupService(
            upload_root=upload_root,
            allowed_extensions={"mp4"},
            ttl_seconds=60,
            scan_interval_seconds=60,
            logger_obj=logging.getLogger("test.upload.cleanup.locked"),
            session_cleanup=session_cleanup,
            protected_paths_provider=protected_paths,
            operation_lock=operation_lock,
        )

        assert cleanup.cleanup_once() == 1
        assert pending_path.exists()
        assert not stale_path.exists()
        assert ("sessions", True, "") in observed
        assert ("protected", True, "") in observed
        assert ("unlink", True, "stale.mp4") in observed
