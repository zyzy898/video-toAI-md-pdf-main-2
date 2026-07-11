import gc
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.task_store import TaskConflictError, TaskLeaseLostError, TaskStateError, TaskStore


@pytest.fixture
def clock():
    value = [1_000.0]
    return value, lambda: value[0]


@pytest.fixture
def store(tmp_path, clock):
    task_store = TaskStore(tmp_path / "tasks.db", clock=clock[1])
    yield task_store
    task_store.close()


def test_initializes_sqlite_and_returns_only_public_fields(store, tmp_path):
    snapshot = store.create_task(
        "owner-a",
        "single",
        {"source": "video.mp4", "api_key": "secret", "nested": {"token": "x"}},
        task_id="task-1",
    )

    assert snapshot["task_id"] == "task-1"
    assert snapshot["status"] == "queued"
    assert snapshot["request"] == {"source": "video.mp4", "nested": {}}
    assert "request_json" not in snapshot
    assert "request_hash" not in snapshot

    connection = sqlite3.connect(tmp_path / "tasks.db")
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
    finally:
        connection.close()
    assert {"heartbeat_at", "attempt_count", "revision", "recovery_count"} <= columns


def test_concurrent_startup_migrates_legacy_progress_schema_once(tmp_path):
    errors = []
    for iteration in range(20):
        database_path = tmp_path / f"legacy-{iteration}.db"
        seed = TaskStore(database_path)
        seed.close()
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("ALTER TABLE tasks DROP COLUMN file_progress_json")
            connection.commit()
        finally:
            connection.close()

        barrier = threading.Barrier(2)

        def open_store():
            barrier.wait()
            task_store = TaskStore(database_path)
            try:
                assert task_store.create_task(
                    "owner-a",
                    "batch",
                    {"filepaths": ["uploads/a.mp4"]},
                    task_id=f"task-{iteration}",
                )["file_progress"] == []
            finally:
                task_store.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(open_store) for _ in range(2)]
            for future in futures:
                try:
                    future.result()
                except Exception as exc:  # pragma: no branch - failures are asserted together
                    errors.append(exc)
        gc.collect()

    assert errors == []


def test_create_is_idempotent_but_rejects_changed_payload(store):
    first = store.create_task("owner-a", "url", {"url": "https://example.com"}, task_id="same")
    again = store.create_task("owner-a", "url", {"url": "https://example.com"}, task_id="same")

    assert again == first
    with pytest.raises(TaskConflictError):
        store.create_task("owner-a", "url", {"url": "https://other.example"}, task_id="same")


def test_owner_isolation_latest_and_queue_listing(store, clock):
    store.create_task("owner-a", "single", {"n": 1}, task_id="a1")
    clock[0][0] += 1
    store.create_task("owner-a", "batch", {"n": 2}, task_id="a2")
    store.create_task("owner-b", "single", {"n": 3}, task_id="b1")

    assert store.get_task("owner-b", "a1") is None
    assert store.latest_task("owner-a")["task_id"] == "a2"
    assert [item["task_id"] for item in store.list_queued(owner_id="owner-a")] == ["a1", "a2"]


def test_list_tasks_is_owner_scoped_newest_first_and_does_not_load_results(
    store, clock, tmp_path
):
    store.create_task(
        "owner-a",
        "single",
        {
            "filepath": "uploads/old.mp4",
            "api_key": "must-not-leak",
            "nested": {"token": "also-secret", "keep": "visible"},
        },
        task_id="old",
        status="analyzing",
    )
    store.complete_task("owner-a", "old", {"large": "result"})
    clock[0][0] += 1
    store.create_task(
        "owner-a",
        "batch",
        {"filepaths": ["uploads/first.mp4"]},
        task_id="same-time-first",
    )
    store.create_task(
        "owner-b",
        "single",
        {"filepath": "uploads/other-owner.mp4"},
        task_id="other-owner",
    )
    store.create_task(
        "owner-a",
        "url",
        {"url": "https://example.test/video"},
        task_id="same-time-last",
    )

    connection = sqlite3.connect(tmp_path / "tasks.db")
    try:
        connection.execute(
            "UPDATE tasks SET result_json = ? WHERE owner_id = ? AND task_id = ?",
            ("{invalid-json", "owner-a", "old"),
        )
        connection.commit()
    finally:
        connection.close()

    tasks = store.list_tasks("owner-a")

    assert [task["task_id"] for task in tasks] == [
        "same-time-last",
        "same-time-first",
        "old",
    ]
    assert tasks[-1]["request"] == {
        "filepath": "uploads/old.mp4",
        "nested": {"keep": "visible"},
    }
    assert all(
        {
            "owner_id",
            "request_json",
            "request_hash",
            "result",
            "result_json",
            "idempotency_key",
            "claimed_by",
        }.isdisjoint(task)
        for task in tasks
    )


def test_claim_progress_complete_and_terminal_progress_protection(store):
    created = store.create_task("owner-a", "batch", {"files": ["a.mp4"]}, task_id="task")
    claimed = store.claim_next_task("runner-1")
    progressed = store.update_progress(
        "owner-a", "task", stage="transcribing", message="working", percent=50, total=2, current=1
    )
    completed = store.complete_task("owner-a", "task", {"markdown": "done"})

    assert claimed["status"] == "analyzing"
    assert progressed["percent"] == 50
    assert completed["status"] == "completed"
    assert completed["result"] == {"markdown": "done"}
    assert completed["revision"] > progressed["revision"] > claimed["revision"] > created["revision"]
    with pytest.raises(TaskStateError):
        store.update_progress("owner-a", "task", percent=90)
    assert store.get_task("owner-a", "task")["status"] == "completed"


def test_batch_file_progress_is_cumulative_and_current_never_moves_backwards(store):
    store.create_task(
        "owner-a",
        "batch",
        {"filepaths": ["uploads/test1.mp4", "uploads/test2.mp4"]},
        task_id="batch-task",
    )
    store.claim_next_task("runner-1")

    first = store.update_progress(
        "owner-a",
        "batch-task",
        total=2,
        current=1,
        current_file="test1.mp4",
        file_progress=[
            {
                "index": 1,
                "filename": "test1.mp4",
                "status": "success",
                "stage": "done",
                "message": "test1.mp4 分析完成",
            },
            {
                "index": 2,
                "filename": "test2.mp4",
                "status": "analyzing",
                "stage": "analysis",
                "message": "正在分析 test2.mp4",
            },
        ],
    )
    late_worker_update = store.update_progress(
        "owner-a",
        "batch-task",
        current=0,
        current_file="test2.mp4",
        stage="subtitle",
        message="正在识别 test2.mp4 字幕",
    )

    assert first["file_progress"][0]["status"] == "success"
    assert late_worker_update["current"] == 1
    assert late_worker_update["file_progress"] == first["file_progress"]


def test_cancel_request_wins_race_with_completion(store):
    store.create_task("owner-a", "single", {}, task_id="task")
    store.claim_next_task("runner-1")
    requested = store.request_cancel("owner-a", "task")
    finished = store.complete_task("owner-a", "task", {"late": True})

    assert requested["cancel_requested"] is True
    assert finished["status"] == "cancelled"
    assert finished["result"] is None


def test_failed_retryable_task_reuses_same_id_and_can_be_claimed(store):
    store.create_task("owner-a", "single", {}, task_id="task")
    store.claim_next_task("runner-1")
    failed = store.fail_task(
        "owner-a", "task", error_code="provider_busy", error_message="busy", error_http_status=503, retryable=True
    )
    retried = store.retry_task("owner-a", "task")

    assert failed["status"] == "failed"
    assert retried["task_id"] == "task"
    assert retried["status"] == "queued"
    assert retried["error_code"] is None
    assert store.claim_next_task("runner-2")["attempt_count"] == 2


def test_non_retryable_failure_and_illegal_completion_raise(store):
    store.create_task("owner-a", "single", {}, task_id="task")
    with pytest.raises(TaskStateError):
        store.complete_task("owner-a", "task", {})
    store.claim_next_task("runner")
    store.fail_task("owner-a", "task", error_code="bad_input", error_message="bad", retryable=False)
    with pytest.raises(TaskStateError):
        store.retry_task("owner-a", "task")


def test_failure_message_is_redacted_and_bounded_before_persistence(store, tmp_path):
    secrets = ["key-value-123", "token-value-456", "auth-value-789", "pass-value", "url-value"]
    message = (
        "api_key=key-value-123 token: token-value-456 "
        "Authorization: Bearer auth-value-789 password='pass-value' "
        "source=https://example.test/path?safe=visible&secret=url-value "
        + "x" * 5_000
    )
    store.create_task("owner-a", "single", {}, task_id="failed")
    claim = store.claim_next_task("runner")

    failed = store.fail_task(
        "owner-a",
        "failed",
        error_code="provider_error",
        error_message=message,
        expected_attempt=claim["attempt_count"],
    )

    assert "[REDACTED]" in failed["error_message"]
    assert len(failed["error_message"]) <= 2_000
    assert failed["message"] == failed["error_message"]
    connection = sqlite3.connect(tmp_path / "tasks.db")
    try:
        persisted = connection.execute(
            "SELECT message, error_message FROM tasks WHERE owner_id = ? AND task_id = ?",
            ("owner-a", "failed"),
        ).fetchone()
    finally:
        connection.close()
    for secret in secrets:
        assert secret not in failed["error_message"]
        assert secret not in persisted[0]
        assert secret not in persisted[1]


def test_recover_stale_analyzing_tasks_only(store, clock):
    store.create_task(
        "owner-a",
        "batch",
        {"filepaths": ["uploads/old.mp4", "uploads/new.mp4"]},
        task_id="stale",
    )
    store.claim_next_task("runner-1")
    store.update_progress(
        "owner-a",
        "stale",
        percent=50,
        total=2,
        current=1,
        current_file="old.mp4",
        file_progress=[
            {
                "index": 1,
                "filename": "old.mp4",
                "status": "success",
                "stage": "done",
                "message": "old.mp4 分析完成",
            }
        ],
    )
    clock[0][0] += 100
    store.create_task("owner-a", "single", {}, task_id="fresh")
    store.claim_next_task("runner-1")

    recovered = store.recover_stale_tasks(stale_after_seconds=50)

    assert recovered == 1
    stale = store.get_task("owner-a", "stale")
    assert stale["status"] == "queued"
    assert stale["recovery_count"] == 1
    assert stale["percent"] == 0
    assert stale["current"] == 0
    assert stale["current_file"] == ""
    assert stale["file_progress"] == []
    assert store.get_task("owner-a", "fresh")["status"] == "analyzing"


def test_recover_stale_cancel_requested_task_as_cancelled(store, clock):
    store.create_task("owner-a", "single", {}, task_id="cancelled-worker")
    store.claim_next_task("runner-1")
    store.request_cancel("owner-a", "cancelled-worker")
    clock[0][0] += 100

    recovered = store.recover_stale_tasks(stale_after_seconds=50)

    snapshot = store.get_task("owner-a", "cancelled-worker")
    assert recovered == 1
    assert snapshot["status"] == "cancelled"
    assert snapshot["retryable"] is True
    assert snapshot["recovery_count"] == 1


def test_reclaimed_attempt_fences_every_old_worker_write(store, clock):
    store.create_task("owner-a", "single", {}, task_id="fenced")
    old_claim = store.claim_next_task("runner-old")
    clock[0][0] += 100
    assert store.recover_stale_tasks(stale_after_seconds=50) == 1
    with pytest.raises(TaskLeaseLostError):
        store.update_progress(
            "owner-a", "fenced", percent=80, expected_attempt=old_claim["attempt_count"]
        )
    new_claim = store.claim_next_task("runner-new")

    assert old_claim["attempt_count"] == 1
    assert new_claim["attempt_count"] == 2
    with pytest.raises(TaskLeaseLostError):
        store.update_progress(
            "owner-a", "fenced", percent=90, expected_attempt=old_claim["attempt_count"]
        )
    with pytest.raises(TaskLeaseLostError):
        store.complete_task(
            "owner-a", "fenced", {"worker": "old"}, expected_attempt=old_claim["attempt_count"]
        )
    with pytest.raises(TaskLeaseLostError):
        store.fail_task(
            "owner-a",
            "fenced",
            error_code="old_failure",
            error_message="old worker failed",
            expected_attempt=old_claim["attempt_count"],
        )
    with pytest.raises(TaskLeaseLostError):
        store.confirm_cancelled(
            "owner-a", "fenced", expected_attempt=old_claim["attempt_count"]
        )

    current = store.get_task("owner-a", "fenced")
    assert current["status"] == "analyzing"
    assert current["percent"] == 0
    completed = store.complete_task(
        "owner-a", "fenced", {"worker": "new"}, expected_attempt=new_claim["attempt_count"]
    )
    assert completed["status"] == "completed"
    assert completed["result"] == {"worker": "new"}


def test_claim_is_atomic_across_store_instances(tmp_path):
    first = TaskStore(tmp_path / "shared.db")
    second = TaskStore(tmp_path / "shared.db")
    try:
        first.create_task("owner", "single", {}, task_id="only")
        assert first.claim_next_task("runner-a")["task_id"] == "only"
        assert second.claim_next_task("runner-b") is None
    finally:
        first.close()
        second.close()
