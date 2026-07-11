"""Route-level coverage for resumable upload lifecycle behavior."""

from __future__ import annotations

import io
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

import app
from services.upload_session import UploadSessionService, UploadVideoAutoCleanupService


@pytest.fixture()
def upload_client(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    staging_root = upload_root / ".staging"
    session_root = upload_root / ".upload_sessions"
    for path in (upload_root, staging_root, session_root):
        path.mkdir(parents=True, exist_ok=True)

    memory_buffers = {}
    memory_reserved_bytes = {}
    service = UploadSessionService(
        session_root=session_root,
        memory_buffers=memory_buffers,
        memory_reserved_bytes=memory_reserved_bytes,
        max_memory_total_bytes=1024 * 1024,
        logger_obj=logging.getLogger("test.upload.lifecycle"),
    )
    monkeypatch.setattr(app, "UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(app, "UPLOAD_STAGING_ROOT", staging_root)
    monkeypatch.setattr(app, "upload_session_service", service)
    monkeypatch.setattr(app, "upload_memory_buffers", memory_buffers)
    monkeypatch.setattr(app, "upload_memory_reserved_bytes", memory_reserved_bytes)
    monkeypatch.setattr(app, "upload_memory_reserved_total_bytes", 0)
    monkeypatch.setattr(app, "is_valid_video_content", lambda _path: True)
    monkeypatch.setattr(
        app,
        "_build_video_segment_policy",
        lambda _path: {"requires_trim": False, "zone": "standard"},
    )
    monkeypatch.setattr(
        app,
        "_check_upload_blacklist_precheck",
        lambda *, staged_video_path, **_kwargs: (
            None,
            app._compute_file_sha256(staged_video_path),
        ),
    )
    monkeypatch.setattr(
        app,
        "_run_upload_pre_risk_check",
        lambda *, file_fingerprint="", **_kwargs: (
            {"decision": "allow", "risk_level": "low", "reason_code": "ALLOW"},
            file_fingerprint,
            "deferred",
        ),
    )
    monkeypatch.setattr(app, "_mark_uploaded_video_loaded_now", lambda _path: None)
    return app.app.test_client(), service


def _init_upload(client, *, upload_id: str = "") -> dict:
    response = client.post(
        "/upload_chunk_init",
        json={
            "filename": "clip.mp4",
            "total_size": 4,
            "chunk_size": 256 * 1024,
            "file_key": "clip.mp4:4:123",
            "upload_id": upload_id,
        },
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_resumable_uploads_always_use_disk_storage(upload_client):
    client, _service = upload_client

    initialized = _init_upload(client)

    assert initialized["storage_mode"] == "disk"
    assert initialized["status"] == "uploading"


def test_reselecting_same_file_resumes_chunks_after_service_restart(
    upload_client, monkeypatch
):
    client, service = upload_client
    initialized = _init_upload(client)
    upload_id = initialized["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()

    restarted_service = UploadSessionService(
        session_root=service.session_root,
        memory_buffers={},
        memory_reserved_bytes={},
        max_memory_total_bytes=1024 * 1024,
        logger_obj=logging.getLogger("test.upload.lifecycle.restarted"),
    )
    monkeypatch.setattr(app, "upload_session_service", restarted_service)
    monkeypatch.setattr(app, "upload_memory_buffers", restarted_service.memory_buffers)
    monkeypatch.setattr(
        app, "upload_memory_reserved_bytes", restarted_service.memory_reserved_bytes
    )

    resumed = _init_upload(client, upload_id=upload_id)

    assert resumed["upload_id"] == upload_id
    assert resumed["received_chunks"] == [0]
    assert resumed["storage_mode"] == "disk"


def test_upload_cancel_removes_session_and_partial_file_idempotently(upload_client):
    client, service = upload_client
    initialized = _init_upload(client)
    upload_id = initialized["upload_id"]
    service.session_temp_path(upload_id).write_bytes(b"partial")

    first = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})
    second = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert first.status_code == 200
    assert first.get_json()["status"] == "cancelled"
    assert second.status_code == 200
    assert second.get_json()["status"] == "cancelled"
    assert not service.session_json_path(upload_id).exists()
    assert not service.session_temp_path(upload_id).exists()


def test_upload_cancel_rejects_alias_without_deleting_other_session(upload_client):
    client, service = upload_client
    initialized = _init_upload(client)
    upload_id = initialized["upload_id"]

    response = client.post("/upload_chunk_cancel", json={"upload_id": f"../{upload_id}"})

    assert response.status_code == 400
    assert service.session_json_path(upload_id).exists()


def test_upload_cancel_removes_orphan_partial_without_session_json(upload_client):
    client, service = upload_client
    upload_id = "orphan-part"
    service.session_temp_path(upload_id).write_bytes(b"partial")

    response = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert response.status_code == 200
    assert response.get_json()["status"] == "cancelled"
    assert not service.session_temp_path(upload_id).exists()


def test_upload_cancel_reports_unconfirmed_when_delete_fails(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    monkeypatch.setattr(service, "delete", lambda _upload_id: False)

    response = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert response.status_code == 500
    assert response.get_json() == {
        "success": False,
        "upload_id": upload_id,
        "status": "cancel_unconfirmed",
        "error": "上传取消未确认，请稍后重试",
    }


def test_upload_cancel_removes_recovered_finalizing_destination(upload_client):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "pending.mp4"
    pending_path.write_bytes(b"data")
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"data").hexdigest()
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)

    response = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert response.status_code == 200
    assert response.get_json()["status"] == "cancelled"
    assert not pending_path.exists()
    assert service.load(upload_id) is None


def test_upload_cancel_keeps_finalizing_session_when_destination_delete_fails(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "locked.mp4"
    pending_path.write_bytes(b"data")
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"data").hexdigest()
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)
    real_unlink = Path.unlink

    def fail_pending_unlink(path, *args, **kwargs):
        if path == pending_path:
            raise PermissionError("simulated locked destination")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_pending_unlink)

    response = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert response.status_code == 500
    assert response.get_json()["status"] == "cancel_unconfirmed"
    assert pending_path.exists()
    assert service.load(upload_id)["status"] == "finalizing"


def test_upload_cancel_does_not_delete_reused_pending_destination(upload_client):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "reused.mp4"
    pending_path.write_bytes(b"same")
    old_identity = app._upload_path_identity(pending_path)
    pending_path.unlink()
    pending_path.write_bytes(b"same")
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"same").hexdigest()
    session["pending_destination_identity"] = old_identity
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)

    response = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert response.status_code == 500
    assert response.get_json()["status"] == "cancel_unconfirmed"
    assert pending_path.read_bytes() == b"same"
    assert service.load(upload_id)["status"] == "finalizing"


def test_upload_cancel_retry_does_not_delete_same_content_replacement_after_session_delete_failure(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "same-content.mp4"
    pending_path.write_bytes(b"same")
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"same").hexdigest()
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)
    monkeypatch.setattr(service, "delete", lambda _upload_id: False)

    first = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert first.status_code == 500
    assert not pending_path.exists()
    pending_path.write_bytes(b"same")

    second = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert second.status_code == 500
    assert second.get_json()["status"] == "cancel_unconfirmed"
    assert pending_path.read_bytes() == b"same"


def test_upload_cancel_missing_target_tombstone_protects_later_replacement(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "missing-then-reused.mp4"
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"same").hexdigest()
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)
    monkeypatch.setattr(service, "delete", lambda _upload_id: False)

    first = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert first.status_code == 500
    persisted = service.load(upload_id)
    assert persisted["pending_destination_deleted"] is True
    pending_path.write_bytes(b"same")

    second = client.post("/upload_chunk_cancel", json={"upload_id": upload_id})

    assert second.status_code == 500
    assert pending_path.read_bytes() == b"same"


def test_upload_finalize_can_be_retried_after_response_loss(upload_client):
    client, service = upload_client
    initialized = _init_upload(client)
    upload_id = initialized["upload_id"]
    chunk_response = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert chunk_response.status_code == 200, chunk_response.get_json()

    first = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})
    second = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert first.status_code == 200, first.get_json()
    assert second.status_code == 200, second.get_json()
    assert second.get_json() == first.get_json()
    assert first.get_json()["status"] == "completed"
    completed_session = service.load(upload_id)
    assert completed_session is not None
    assert completed_session["status"] == "completed"
    assert completed_session["result_file_sha256"] == hashlib.sha256(b"data").hexdigest()
    assert isinstance(completed_session["result_destination_identity"], dict)
    assert not service.session_temp_path(upload_id).exists()


def test_completed_receipt_rejects_same_content_replacement(upload_client):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    completed = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})
    assert completed.status_code == 200, completed.get_json()
    result_path = Path(completed.get_json()["filepath"])
    result_path.unlink()
    result_path.write_bytes(b"data")

    replay = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert replay.status_code == 410
    assert replay.get_json()["status"] == "expired"
    assert result_path.read_bytes() == b"data"
    assert service.load(upload_id) is None


def test_completed_receipt_with_outside_path_expires(upload_client):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    completed = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})
    assert completed.status_code == 200, completed.get_json()
    outside_path = service.session_root.parent.parent / "outside.mp4"
    outside_path.write_bytes(b"data")
    completed_session = service.load(upload_id)
    completed_session["result"] = {
        "filepath": str(outside_path),
        "filename": outside_path.name,
    }
    service.save(upload_id, completed_session)

    replay = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert replay.status_code == 410
    assert replay.get_json()["status"] == "expired"
    assert outside_path.read_bytes() == b"data"
    assert service.load(upload_id) is None


def test_completed_init_starts_new_session_when_result_is_missing(upload_client):
    client, _service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    completed = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})
    assert completed.status_code == 200, completed.get_json()
    Path(completed.get_json()["filepath"]).unlink()

    resumed = _init_upload(client, upload_id=upload_id)

    assert resumed["upload_id"] != upload_id
    assert resumed["status"] == "uploading"


def test_concurrent_same_name_finalize_never_overwrites(upload_client, monkeypatch):
    client, service = upload_client
    upload_ids = []
    for payload in (b"aaaa", b"bbbb"):
        upload_id = _init_upload(client)["upload_id"]
        uploaded = client.post(
            "/upload_chunk",
            data={
                "upload_id": upload_id,
                "chunk_index": "0",
                "chunk": (io.BytesIO(payload), "chunk.bin"),
            },
            content_type="multipart/form-data",
        )
        assert uploaded.status_code == 200, uploaded.get_json()
        upload_ids.append(upload_id)

    old_reserve = service.reserve_unique_destination
    race_barrier = Barrier(2)

    def race_atomic_reservation(filename, *, upload_root, reservation_token=None):
        path = old_reserve(
            filename,
            upload_root=upload_root,
            reservation_token=reservation_token,
        )
        race_barrier.wait(timeout=5)
        return path

    monkeypatch.setattr(service, "reserve_unique_destination", race_atomic_reservation)

    def finalize(upload_id):
        with app.app.test_client() as concurrent_client:
            response = concurrent_client.post(
                "/upload_chunk_finalize", json={"upload_id": upload_id}
            )
            return response.status_code, response.get_json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(finalize, upload_ids))

    assert [status for status, _payload in responses] == [200, 200]
    result_names = {payload["filename"] for _status, payload in responses}
    assert len(result_names) == 2
    assert all(
        upload_id in payload["filename"]
        for upload_id, (_status, payload) in zip(upload_ids, responses)
    )
    result_contents = {
        (service.session_root.parent / name).read_bytes() for name in result_names
    }
    assert result_contents == {b"aaaa", b"bbbb"}


def test_finalize_recovers_after_crash_between_move_and_receipt(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()

    class SimulatedProcessCrash(BaseException):
        pass

    original_save = service.save

    def crash_before_completed_receipt(saved_upload_id, session):
        if session.get("status") == "completed":
            raise SimulatedProcessCrash
        original_save(saved_upload_id, session)

    monkeypatch.setattr(service, "save", crash_before_completed_receipt)

    with pytest.raises(SimulatedProcessCrash):
        client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    interrupted_session = service.load(upload_id)
    assert interrupted_session["status"] == "finalizing"
    pending_result = interrupted_session["pending_result"]
    moved_path = service.session_root.parent / pending_result["filename"]
    assert moved_path.read_bytes() == b"data"

    restarted_service = UploadSessionService(
        session_root=service.session_root,
        memory_buffers={},
        memory_reserved_bytes={},
        max_memory_total_bytes=1024 * 1024,
        logger_obj=logging.getLogger("test.upload.lifecycle.crash-restart"),
    )
    monkeypatch.setattr(app, "upload_session_service", restarted_service)
    monkeypatch.setattr(app, "upload_memory_buffers", restarted_service.memory_buffers)
    monkeypatch.setattr(
        app, "upload_memory_reserved_bytes", restarted_service.memory_reserved_bytes
    )
    monkeypatch.setattr(
        app,
        "_run_upload_pre_risk_check",
        lambda **_kwargs: pytest.fail("recovery must not rerun upload risk checks"),
    )

    recovered = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert recovered.status_code == 200, recovered.get_json()
    assert recovered.get_json() == pending_result
    completed_session = restarted_service.load(upload_id)
    assert completed_session["status"] == "completed"
    assert completed_session["result"] == pending_result
    assert "pending_result" not in completed_session
    assert [path.name for path in service.session_root.parent.glob("clip*.mp4")] == [
        pending_result["filename"]
    ]


def test_finalize_recovers_after_crash_after_pending_before_move(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()

    class SimulatedProcessCrash(BaseException):
        pass

    real_replace = app.os.replace

    def crash_before_video_move(source, destination):
        if str(destination).endswith(".mp4"):
            raise SimulatedProcessCrash
        return real_replace(source, destination)

    monkeypatch.setattr(app.os, "replace", crash_before_video_move)
    with pytest.raises(SimulatedProcessCrash):
        client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    interrupted_session = service.load(upload_id)
    pending_result = interrupted_session["pending_result"]
    reserved_path = service.session_root.parent / pending_result["filename"]
    assert reserved_path.read_bytes() == b""
    assert service.session_temp_path(upload_id).read_bytes() == b"data"

    restarted_service = UploadSessionService(
        session_root=service.session_root,
        memory_buffers={},
        memory_reserved_bytes={},
        max_memory_total_bytes=1024 * 1024,
        logger_obj=logging.getLogger("test.upload.lifecycle.pending-restart"),
    )
    monkeypatch.setattr(app, "upload_session_service", restarted_service)
    monkeypatch.setattr(app, "upload_memory_buffers", restarted_service.memory_buffers)
    monkeypatch.setattr(
        app, "upload_memory_reserved_bytes", restarted_service.memory_reserved_bytes
    )
    monkeypatch.setattr(app.os, "replace", real_replace)
    monkeypatch.setattr(
        app,
        "_run_upload_pre_risk_check",
        lambda **_kwargs: pytest.fail("pending move recovery must not rerun risk checks"),
    )

    recovered = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert recovered.status_code == 200, recovered.get_json()
    assert recovered.get_json() == pending_result
    assert reserved_path.read_bytes() == b"data"
    assert not restarted_service.session_temp_path(upload_id).exists()


def test_finalize_does_not_claim_reused_pending_destination(upload_client):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "reused.mp4"
    pending_path.write_bytes(b"same")
    old_identity = app._upload_path_identity(pending_path)
    pending_path.unlink()
    pending_path.write_bytes(b"same")
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"same").hexdigest()
    session["pending_destination_identity"] = old_identity
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)

    response = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert response.status_code == 409
    assert response.get_json()["status"] == "finalizing"
    assert pending_path.read_bytes() == b"same"
    assert service.load(upload_id)["status"] == "finalizing"


def test_full_file_recovery_refreshes_mtime_before_completed_receipt(
    upload_client, monkeypatch
):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    pending_path = service.session_root.parent / "stale-pending.mp4"
    pending_path.write_bytes(b"data")
    old_mtime = 1.0
    os.utime(pending_path, (old_mtime, old_mtime))
    session = service.load(upload_id)
    session["status"] = "finalizing"
    session["pending_result"] = {
        "success": True,
        "status": "completed",
        "filename": pending_path.name,
        "filepath": str(pending_path),
    }
    session["pending_file_sha256"] = hashlib.sha256(b"data").hexdigest()
    service.save(upload_id, session)
    app.upload_finalizing_ids.discard(upload_id)
    monkeypatch.setattr(app, "_mark_uploaded_video_loaded_now", lambda path: os.utime(path, None))
    observed_mtimes = []
    original_save = service.save

    class SimulatedProcessCrash(BaseException):
        pass

    def crash_at_completed_receipt(saved_upload_id, saved_session):
        if saved_session.get("status") == "completed":
            observed_mtimes.append(pending_path.stat().st_mtime)
            raise SimulatedProcessCrash
        original_save(saved_upload_id, saved_session)

    monkeypatch.setattr(service, "save", crash_at_completed_receipt)

    with pytest.raises(SimulatedProcessCrash):
        client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert observed_mtimes and observed_mtimes[0] > old_mtime


def test_move_identity_crash_does_not_allow_new_session_to_reuse_path(
    upload_client, monkeypatch
):
    client, service = upload_client
    first_upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": first_upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()

    class SimulatedProcessCrash(BaseException):
        pass

    original_persist_identity = app._persist_pending_destination_identity

    def crash_before_moved_identity(*_args, **_kwargs):
        raise SimulatedProcessCrash

    monkeypatch.setattr(
        app,
        "_persist_pending_destination_identity",
        crash_before_moved_identity,
    )
    with pytest.raises(SimulatedProcessCrash):
        client.post("/upload_chunk_finalize", json={"upload_id": first_upload_id})
    first_session = service.load(first_upload_id)
    first_path = Path(first_session["pending_result"]["filepath"])
    assert first_path.exists()
    first_path.unlink()

    monkeypatch.setattr(
        app,
        "_persist_pending_destination_identity",
        original_persist_identity,
    )
    second_upload_id = _init_upload(client)["upload_id"]
    second_uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": second_upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert second_uploaded.status_code == 200, second_uploaded.get_json()
    second_completed = client.post(
        "/upload_chunk_finalize",
        json={"upload_id": second_upload_id},
    )

    assert second_completed.status_code == 200, second_completed.get_json()
    second_path = Path(second_completed.get_json()["filepath"])
    assert second_path != first_path
    assert first_upload_id in first_path.name
    assert second_upload_id in second_path.name


def test_video_cleanup_reconciles_receipt_after_deleting_stale_result(upload_client):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    completed = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})
    result_path = Path(completed.get_json()["filepath"])
    os.utime(result_path, (1.0, 1.0))

    cleanup = UploadVideoAutoCleanupService(
        upload_root=service.session_root.parent,
        allowed_extensions={"mp4"},
        ttl_seconds=60,
        scan_interval_seconds=60,
        logger_obj=logging.getLogger("test.upload.lifecycle.cleanup"),
        session_cleanup=lambda: service.cleanup_stale_sessions(
            upload_root=service.session_root.parent,
            ttl_seconds=60,
        ),
        protected_paths_provider=lambda: service.pending_destination_paths(
            upload_root=service.session_root.parent
        ),
        operation_lock=app.upload_session_lock,
    )

    assert cleanup.cleanup_once() == 1
    assert not result_path.exists()
    assert service.load(upload_id) is None


def test_chunk_finalize_moves_destination_while_holding_upload_lock(
    upload_client, monkeypatch
):
    client, _service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()
    real_replace = app.os.replace
    observed = []

    def observe_replace(source, destination):
        if str(destination).endswith(".mp4"):
            observed.append(app.upload_session_lock._is_owned())
        return real_replace(source, destination)

    monkeypatch.setattr(app.os, "replace", observe_replace)

    response = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert response.status_code == 200, response.get_json()
    assert observed == [True]


def test_finalize_move_error_keeps_pending_state_for_retry(upload_client, monkeypatch):
    client, service = upload_client
    upload_id = _init_upload(client)["upload_id"]
    uploaded = client.post(
        "/upload_chunk",
        data={
            "upload_id": upload_id,
            "chunk_index": "0",
            "chunk": (io.BytesIO(b"data"), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_json()

    real_replace = app.os.replace

    def fail_video_move(source, destination):
        if str(destination).endswith(".mp4"):
            raise OSError("simulated move failure")
        return real_replace(source, destination)

    monkeypatch.setattr(app.os, "replace", fail_video_move)
    failed = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert failed.status_code == 500
    interrupted_session = service.load(upload_id)
    pending_result = interrupted_session["pending_result"]
    assert service.session_temp_path(upload_id).read_bytes() == b"data"
    assert (service.session_root.parent / pending_result["filename"]).exists()

    monkeypatch.setattr(app.os, "replace", real_replace)
    recovered = client.post("/upload_chunk_finalize", json={"upload_id": upload_id})

    assert recovered.status_code == 200, recovered.get_json()
    assert recovered.get_json() == pending_result


def test_upload_session_cleanup_runs_under_upload_lock(upload_client, monkeypatch):
    _client, service = upload_client
    observed = []

    def cleanup_stale_sessions(**kwargs):
        observed.append((app.upload_session_lock._is_owned(), kwargs))
        return 3

    monkeypatch.setattr(service, "cleanup_stale_sessions", cleanup_stale_sessions)

    assert app._cleanup_upload_sessions_once() == 3
    assert observed == [
        (
            True,
            {
                "upload_root": app.UPLOAD_ROOT,
                "ttl_seconds": app.UPLOAD_VIDEO_AUTO_DELETE_TTL_SECONDS,
            },
        )
    ]
