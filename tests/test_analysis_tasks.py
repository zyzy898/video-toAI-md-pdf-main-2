import threading
import time
from pathlib import Path

import pytest

import app as app_module
import config
from services.task_runner import TaskRunner
from services.task_store import TaskStore


OWNER_A = {"X-Client-ID": "owner-a"}
OWNER_B = {"X-Client-ID": "owner-b"}


@pytest.fixture
def task_api(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "analysis-tasks.db")
    runner = TaskRunner(
        store,
        app_module._execute_analysis_task,
        runner_id="api-test-runner",
    )
    monkeypatch.setattr(app_module, "analysis_task_store", store)
    monkeypatch.setattr(app_module, "analysis_task_runner", runner)
    monkeypatch.setitem(app_module.app.config, "TESTING", True)
    monkeypatch.setattr(app_module, "_start_upload_video_auto_cleanup", lambda: None)
    monkeypatch.setattr(app_module, "_start_history_retention_cleanup", lambda: None)
    try:
        yield app_module.app.test_client(), store, runner
    finally:
        runner.stop()
        store.close()


def _create(client, kind="single", payload=None, *, headers=None, task_id=None):
    request_json = {"kind": kind, "payload": payload or {}}
    if task_id is not None:
        request_json["task_id"] = task_id
    return client.post(
        "/analysis_tasks",
        json=request_json,
        headers=headers or OWNER_A,
    )


def test_analysis_task_config_is_runtime_scoped_and_exported():
    assert config.ANALYSIS_TASK_DB_PATH.parent == config.UPLOAD_ROOT
    assert config.ANALYSIS_TASK_MAX_WORKERS >= 1
    assert config.ANALYSIS_TASK_POLL_INTERVAL_SECONDS > 0
    assert config.ANALYSIS_TASK_STALE_AFTER_SECONDS >= 0
    assert {
        "ANALYSIS_TASK_DB_PATH",
        "ANALYSIS_TASK_MAX_WORKERS",
        "ANALYSIS_TASK_POLL_INTERVAL_SECONDS",
        "ANALYSIS_TASK_STALE_AFTER_SECONDS",
    } <= set(config.__all__)


def test_analysis_task_runtime_shutdown_is_ordered_and_idempotent(monkeypatch):
    events = []

    class FakeRunner:
        def stop(self, wait=True):
            events.append(("stop", wait))
            return True

    class FakeStore:
        def close(self):
            events.append(("close", None))

    monkeypatch.setattr(app_module, "analysis_task_runner", FakeRunner())
    monkeypatch.setattr(app_module, "analysis_task_store", FakeStore())
    monkeypatch.setattr(app_module, "_analysis_task_shutdown_complete", False)

    assert app_module._shutdown_analysis_task_runtime() is True
    assert app_module._shutdown_analysis_task_runtime() is False
    assert events == [("stop", True), ("close", None)]


def test_create_is_202_owner_scoped_and_idempotency_conflicts(task_api):
    client, store, _runner = task_api
    headers = {**OWNER_A, "Idempotency-Key": "same-request"}

    first = _create(
        client,
        payload={"filepath": "uploads/clip.mp4", "summary_only": True},
        headers=headers,
    )
    repeated = _create(
        client,
        payload={"filepath": "uploads/clip.mp4", "summary_only": True},
        headers=headers,
    )
    conflict = _create(
        client,
        payload={"filepath": "uploads/other.mp4", "summary_only": True},
        headers=headers,
    )

    first_payload = first.get_json()
    assert first.status_code == repeated.status_code == 202
    assert repeated.get_json()["task_id"] == first_payload["task_id"]
    assert conflict.status_code == 409
    assert {"payload", "request", "result", "owner_id", "revision"}.isdisjoint(first_payload)
    stored = store.get_task("owner-a", first_payload["task_id"])
    assert stored["request"] == {
        "filepath": "uploads/clip.mp4",
        "output_template": "operation_guide",
        "summary_only": True,
    }


def test_list_analysis_tasks_is_complete_owner_scoped_newest_first_and_safe(task_api):
    client, store, _runner = task_api
    owner_a_task_ids = []
    for index in range(25):
        task_id = f"owner-a-{index:02d}"
        owner_a_task_ids.append(task_id)
        store.create_task(
            "owner-a",
            "single",
            {
                "filepath": f"uploads/clip-{index:02d}.mp4",
                "output_template": "content_summary",
                "api_key": f"secret-{index}",
            },
            task_id=task_id,
        )
    store.create_task(
        "owner-b",
        "url",
        {"url": "https://example.test/private"},
        task_id="owner-b-only",
    )

    response = client.get("/analysis_tasks", headers=OWNER_A)

    assert response.status_code == 200
    payload = response.get_json()
    assert list(payload) == ["tasks"]
    assert [task["task_id"] for task in payload["tasks"]] == list(
        reversed(owner_a_task_ids)
    )
    assert len(payload["tasks"]) == 25
    assert payload["tasks"][0]["payload"] == {
        "filepath": "uploads/clip-24.mp4",
        "output_template": "content_summary",
    }
    assert all(
        {
            "request",
            "result",
            "owner_id",
            "revision",
            "request_json",
            "request_hash",
            "result_json",
            "idempotency_key",
            "claimed_by",
        }.isdisjoint(task)
        for task in payload["tasks"]
    )
    owner_b_response = client.get("/analysis_tasks", headers=OWNER_B)
    assert [task["task_id"] for task in owner_b_response.get_json()["tasks"]] == [
        "owner-b-only"
    ]


def test_create_persists_output_template_and_rejects_invalid_values(task_api):
    client, store, _runner = task_api

    defaulted = _create(
        client,
        payload={"filepath": "uploads/default-guide.mp4"},
    )
    accepted = _create(
        client,
        payload={
            "filepath": "uploads/clip.mp4",
            "output_template": "content_summary",
        },
    )
    rejected = _create(
        client,
        payload={
            "filepath": "uploads/clip.mp4",
            "output_template": "invented_template",
        },
    )

    assert defaulted.status_code == 202
    defaulted_task = store.get_task("owner-a", defaulted.get_json()["task_id"])
    assert defaulted_task["request"]["output_template"] == "operation_guide"
    assert accepted.status_code == 202
    stored = store.get_task("owner-a", accepted.get_json()["task_id"])
    assert stored["request"]["output_template"] == "content_summary"
    assert rejected.status_code == 400
    assert "output_template" in rejected.get_json()["error"]


def test_queued_task_runs_inline_and_result_payload_is_unchanged(task_api, monkeypatch):
    client, store, runner = task_api
    expected = {"success": True, "markdown": "# generated", "steps": [{"step": 1}]}
    observed = {}

    def lightweight_analyze():
        body = app_module.request.get_json()
        observed["body"] = body
        observed["owner"] = app_module.request.headers.get("X-Client-ID")
        app_module._update_single_progress(
            owner_id="owner-a",
            task_id=body["task_id"],
            status="processing",
            stage="analysis",
            message="working",
            current_file="clip.mp4",
        )
        observed["durable"] = store.get_task("owner-a", body["task_id"])
        return app_module.jsonify(expected)

    monkeypatch.setattr(app_module, "analyze", lightweight_analyze)
    created = _create(
        client,
        payload={
            "filepath": "uploads/clip.mp4",
            "output_template": "content_summary",
        },
    )
    task_id = created.get_json()["task_id"]

    assert runner.poll_once(run_inline=True) is True
    status_response = client.get(f"/analysis_tasks/{task_id}", headers=OWNER_A)
    result_response = client.get(f"/analysis_tasks/{task_id}/result", headers=OWNER_A)

    assert observed["owner"] == "owner-a"
    assert observed["body"] == {
        "filepath": "uploads/clip.mp4",
        "output_template": "content_summary",
        "task_id": task_id,
    }
    assert observed["durable"]["status"] == "analyzing"
    assert observed["durable"]["stage"] == "analysis"
    assert 0 < observed["durable"]["percent"] < 100
    assert status_response.status_code == 200
    assert status_response.get_json()["status"] == "completed"
    assert status_response.get_json()["attempt_count"] == 1
    assert status_response.get_json()["recovery_count"] == 0
    assert {"request", "result", "owner_id", "revision"}.isdisjoint(
        status_response.get_json()
    )
    assert result_response.status_code == 200
    assert result_response.get_json() == expected


def test_failed_result_keeps_http_status_and_retry_requeues_same_task(task_api, monkeypatch):
    client, _store, runner = task_api
    attempts = []

    def flaky_analyze():
        attempts.append(1)
        if len(attempts) == 1:
            return app_module.jsonify({"error": "provider busy", "code": "provider_busy"}), 429
        return app_module.jsonify({"success": True, "markdown": "recovered"})

    monkeypatch.setattr(app_module, "analyze", flaky_analyze)
    created = _create(client, payload={"filepath": "uploads/clip.mp4"})
    task_id = created.get_json()["task_id"]
    assert runner.poll_once(run_inline=True) is True

    failed = client.get(f"/analysis_tasks/{task_id}/result", headers=OWNER_A)
    retried = client.post(f"/analysis_tasks/{task_id}/retry", headers=OWNER_A)

    assert failed.status_code == 429
    assert failed.get_json() == {
        "code": "provider_busy",
        "error": "provider busy",
        "retryable": True,
        "task_id": task_id,
    }
    assert retried.status_code == 202
    assert retried.get_json()["status"] == "queued"
    assert runner.poll_once(run_inline=True) is True
    assert client.get(f"/analysis_tasks/{task_id}/result", headers=OWNER_A).get_json() == {
        "success": True,
        "markdown": "recovered",
    }
    assert client.post(f"/analysis_tasks/{task_id}/retry", headers=OWNER_A).status_code == 409


def test_non_retryable_failure_rejects_retry(task_api, monkeypatch):
    client, _store, runner = task_api
    monkeypatch.setattr(
        app_module,
        "analyze",
        lambda: (app_module.jsonify({"error": "forbidden", "code": "blocked"}), 403),
    )
    task_id = _create(client, payload={"filepath": "uploads/clip.mp4"}).get_json()["task_id"]
    assert runner.poll_once(run_inline=True) is True

    assert client.get(f"/analysis_tasks/{task_id}/result", headers=OWNER_A).status_code == 403
    assert client.post(f"/analysis_tasks/{task_id}/retry", headers=OWNER_A).status_code == 409


def test_queued_cancel_is_immediate_and_result_is_conflict(task_api):
    client, _store, runner = task_api
    task_id = _create(client, payload={"filepath": "uploads/clip.mp4"}).get_json()["task_id"]

    cancelled = client.post(f"/analysis_tasks/{task_id}/cancel", headers=OWNER_A)

    assert cancelled.status_code == 200
    assert cancelled.get_json()["status"] == "cancelled"
    assert client.get(f"/analysis_tasks/{task_id}/result", headers=OWNER_A).status_code == 409
    assert runner.poll_once(run_inline=True) is False


def test_analyzing_cancel_is_confirmed_at_single_progress_boundary(
    task_api, tmp_path, monkeypatch
):
    client, store, runner = task_api
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")

    monkeypatch.setattr(
        app_module,
        "_read_shared_backend_model_options",
        lambda require_api_key=True: ("key", "model", "https://example.test"),
    )
    monkeypatch.setattr(app_module, "_resolve_upload_filepath", lambda raw: video_path)
    monkeypatch.setattr(
        app_module,
        "_build_video_segment_policy",
        lambda path: {"requires_trim": False, "zone": "standard"},
    )
    monkeypatch.setattr(
        app_module,
        "_apply_video_segment_processing_guardrails",
        lambda policy, **options: (
            options["use_video"],
            options["web_search"],
            options["max_vision"],
            options["summary_only"],
            [],
        ),
    )

    def cancel_during_processing(*args, progress_callback=None, **kwargs):
        body = app_module.request.get_json()
        store.request_cancel("owner-a", body["task_id"])
        progress_callback("analysis", "next boundary")
        raise AssertionError("cancelled work continued past progress boundary")

    monkeypatch.setattr(app_module, "process_video", cancel_during_processing)
    task_id = _create(client, payload={"filepath": str(video_path)}).get_json()["task_id"]

    assert runner.poll_once(run_inline=True) is True
    assert store.get_task("owner-a", task_id)["status"] == "cancelled"


def test_batch_worker_does_not_swallow_progress_cancellation(task_api, tmp_path, monkeypatch):
    client, store, runner = task_api
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake")

    monkeypatch.setattr(
        app_module,
        "_read_shared_backend_model_options",
        lambda require_api_key=True: ("key", "model", "https://example.test"),
    )
    monkeypatch.setattr(app_module, "_resolve_upload_filepath", lambda raw: video_path)
    monkeypatch.setattr(
        app_module,
        "_build_video_segment_policy",
        lambda path: {"requires_trim": False, "zone": "standard"},
    )
    monkeypatch.setattr(
        app_module,
        "_evaluate_batch_segment_policy",
        lambda policies: {"allowed": True, "warnings": []},
    )
    monkeypatch.setattr(app_module, "_resolve_batch_analyze_workers", lambda total_files: 1)
    monkeypatch.setattr(
        app_module,
        "_apply_video_segment_processing_guardrails",
        lambda policy, **options: (
            options["use_video"],
            options["web_search"],
            options["max_vision"],
            options["summary_only"],
            [],
        ),
    )

    def cancel_from_batch_worker(*args, progress_callback=None, **kwargs):
        store.request_cancel("owner-a", task_id)
        progress_callback("analysis", "batch boundary")
        raise AssertionError("batch cancellation was swallowed")

    monkeypatch.setattr(app_module, "process_video", cancel_from_batch_worker)
    task_id = _create(client, kind="batch", payload={"filepaths": [str(video_path)]}).get_json()[
        "task_id"
    ]

    assert runner.poll_once(run_inline=True) is True
    assert store.get_task("owner-a", task_id)["status"] == "cancelled"


def test_parallel_batch_status_keeps_completed_and_running_files_separate(
    task_api, tmp_path, monkeypatch
):
    client, store, runner = task_api
    first_path = tmp_path / "test1.mp4"
    second_path = tmp_path / "test2.mp4"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    second_started = threading.Event()
    release_second = threading.Event()

    monkeypatch.setattr(
        app_module,
        "_read_shared_backend_model_options",
        lambda require_api_key=True: ("key", "model", "https://example.test"),
    )
    monkeypatch.setattr(app_module, "_resolve_upload_filepath", lambda raw: Path(raw))
    monkeypatch.setattr(
        app_module,
        "_build_video_segment_policy",
        lambda path: {"requires_trim": False, "zone": "standard"},
    )
    monkeypatch.setattr(
        app_module,
        "_evaluate_batch_segment_policy",
        lambda policies: {"allowed": True, "warnings": []},
    )
    monkeypatch.setattr(app_module, "_resolve_batch_analyze_workers", lambda total_files: 2)
    monkeypatch.setattr(
        app_module,
        "_apply_video_segment_processing_guardrails",
        lambda policy, **options: (
            options["use_video"],
            options["web_search"],
            options["max_vision"],
            options["summary_only"],
            [],
        ),
    )

    def controlled_process_video(filepath, *args, progress_callback=None, **kwargs):
        progress_callback("analysis", f"正在分析 {filepath.name}")
        if filepath.name == "test2.mp4":
            second_started.set()
            assert release_second.wait(2)
        output_dir = tmp_path / f"output-{filepath.stem}"
        return ([{"step": 1}], "# done", str(output_dir), "", True, {})

    monkeypatch.setattr(app_module, "process_video", controlled_process_video)
    task_id = _create(
        client,
        kind="batch",
        payload={"filepaths": [str(first_path), str(second_path)]},
    ).get_json()["task_id"]

    worker = threading.Thread(
        target=lambda: runner.poll_once(run_inline=True),
        daemon=True,
    )
    worker.start()
    try:
        assert second_started.wait(1)
        deadline = time.monotonic() + 2
        partial = None
        while time.monotonic() < deadline:
            snapshot = store.get_task("owner-a", task_id)
            progress = snapshot.get("file_progress", []) if snapshot else []
            if (
                len(progress) == 2
                and progress[0]["status"] == "success"
                and progress[1]["status"] == "analyzing"
            ):
                partial = snapshot
                break
            time.sleep(0.01)

        assert partial is not None
        assert partial["current"] == 1
        assert partial["file_progress"][0]["message"].endswith("test1.mp4 分析完成")
        assert partial["file_progress"][1]["message"] == "正在分析 test2.mp4"
    finally:
        release_second.set()
        worker.join(2)

    assert not worker.is_alive()
    completed = store.get_task("owner-a", task_id)
    assert completed["status"] == "completed"
    assert [item["status"] for item in completed["file_progress"]] == [
        "success",
        "success",
    ]


def test_task_lookup_is_owner_isolated(task_api):
    client, _store, _runner = task_api
    task_id = _create(client, payload={"filepath": "uploads/clip.mp4"}).get_json()["task_id"]

    assert client.get(f"/analysis_tasks/{task_id}", headers=OWNER_B).status_code == 404
    assert client.get(f"/analysis_tasks/{task_id}/result", headers=OWNER_B).status_code == 404
    assert client.post(f"/analysis_tasks/{task_id}/cancel", headers=OWNER_B).status_code == 404
    assert client.post(f"/analysis_tasks/{task_id}/retry", headers=OWNER_B).status_code == 404


def test_legacy_in_memory_progress_still_works_without_task_runner(task_api):
    client, store, _runner = task_api
    app_module._update_single_progress(
        owner_id="owner-a",
        task_id="legacy-task",
        status="processing",
        stage="subtitle",
        message="legacy progress",
        current_file="legacy.mp4",
    )

    response = client.get("/single_progress?task_id=legacy-task", headers=OWNER_A)

    assert response.status_code == 200
    assert response.get_json()["status"] == "processing"
    assert response.get_json()["stage"] == "subtitle"
    assert store.get_task("owner-a", "legacy-task") is None
