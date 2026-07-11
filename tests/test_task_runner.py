import threading
import time
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor

import services.task_runner as task_runner_module
from services.task_runner import TaskCancelledError, TaskRunner
from services.task_store import TaskStore


def _store(tmp_path):
    return TaskStore(tmp_path / "tasks.db")


def _wait_for_status(store, owner_id, task_id, expected, timeout=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = store.get_task(owner_id, task_id)
        if snapshot is not None and snapshot["status"] == expected:
            return snapshot
        time.sleep(0.005)
    raise AssertionError(f"task {task_id} did not reach {expected}")


def test_run_claimed_task_reports_progress_and_completes(tmp_path):
    store = _store(tmp_path)

    def handler(snapshot, cancel_check, progress):
        assert snapshot["request"] == {"source": "video.mp4"}
        assert cancel_check() is False
        progress(stage="transcribing", percent=40, message="working")
        return {"markdown": "ok"}

    try:
        store.create_task("owner", "single", {"source": "video.mp4"}, task_id="task")
        claimed = store.claim_next_task("test-runner")
        result = TaskRunner(store, handler).run_claimed_task(claimed)
        assert result["status"] == "completed"
        assert result["result"] == {"markdown": "ok"}
        assert result["percent"] == 100
    finally:
        store.close()


def test_runner_renews_lease_while_handler_is_blocked_without_progress(tmp_path):
    now = [1_000.0]
    store = TaskStore(tmp_path / "tasks.db", clock=lambda: now[0])
    handler_entered = threading.Event()
    release_handler = threading.Event()
    heartbeat_seen = threading.Event()
    original_update_progress = store.update_progress

    def observe_update_progress(*args, **kwargs):
        snapshot = original_update_progress(*args, **kwargs)
        if handler_entered.is_set():
            heartbeat_seen.set()
        return snapshot

    def handler(snapshot, cancel_check, progress):
        handler_entered.set()
        assert release_handler.wait(2)
        return {"ok": True}

    store.update_progress = observe_update_progress
    runner = TaskRunner(
        store,
        handler,
        max_workers=1,
        poll_interval=0.01,
        stale_after_seconds=0.06,
    )
    try:
        store.create_task("owner", "single", {}, task_id="task")
        assert runner.start() is True
        assert handler_entered.wait(1)

        now[0] += 100
        assert heartbeat_seen.wait(1)
        renewed = store.get_task("owner", "task")
        assert renewed["heartbeat_at"] == now[0]
        assert store.recover_stale_tasks(runner.stale_after_seconds, now=now[0]) == 0
        assert store.get_task("owner", "task")["status"] == "analyzing"

        release_handler.set()
        completed = _wait_for_status(store, "owner", "task", "completed")
        assert completed["attempt_count"] == renewed["attempt_count"]
    finally:
        release_handler.set()
        runner.stop()
        store.close()


def test_cooperative_cancellation_becomes_cancelled(tmp_path):
    store = _store(tmp_path)

    def handler(snapshot, cancel_check, progress):
        store.request_cancel(snapshot["owner_id"], snapshot["task_id"])
        cancel_check()
        raise AssertionError("cancel_check must raise")

    try:
        store.create_task("owner", "single", {}, task_id="task")
        claimed = store.claim_next_task("test-runner")
        result = TaskRunner(store, handler).run_claimed_task(claimed)
        assert result["status"] == "cancelled"
    finally:
        store.close()


def test_handler_exception_is_persisted_as_failure(tmp_path):
    store = _store(tmp_path)

    class RetryableFailure(RuntimeError):
        code = "temporary"
        retryable = True
        http_status = 503

    def handler(snapshot, cancel_check, progress):
        raise RetryableFailure("try later")

    try:
        store.create_task("owner", "single", {}, task_id="task")
        claimed = store.claim_next_task("test-runner")
        result = TaskRunner(store, handler).run_claimed_task(claimed)
        assert result["status"] == "failed"
        assert result["error_code"] == "temporary"
        assert result["error_http_status"] == 503
        assert result["retryable"] is True
    finally:
        store.close()


def test_poll_once_can_run_deterministically_without_dispatch_thread(tmp_path):
    store = _store(tmp_path)

    def handler(snapshot, cancel_check, progress):
        return {"task": snapshot["task_id"]}

    try:
        store.create_task("owner", "url", {"url": "https://example.com"}, task_id="task")
        runner = TaskRunner(store, handler, runner_id="inline")
        assert runner.poll_once(run_inline=True) is True
        assert runner.poll_once(run_inline=True) is False
        assert store.get_task("owner", "task")["status"] == "completed"
    finally:
        store.close()


def test_explicit_task_cancelled_error_is_cooperative(tmp_path):
    store = _store(tmp_path)

    def handler(snapshot, cancel_check, progress):
        raise TaskCancelledError("user stopped")

    try:
        store.create_task("owner", "single", {}, task_id="task")
        claimed = store.claim_next_task("test-runner")
        result = TaskRunner(store, handler).run_claimed_task(claimed)
        assert result["status"] == "cancelled"
    finally:
        store.close()


def test_task_cancelled_error_message_is_redacted_and_bounded(tmp_path):
    store = _store(tmp_path)
    secret = "cancel-secret-value"

    def handler(snapshot, cancel_check, progress):
        raise TaskCancelledError(f"token={secret} " + "x" * 5_000)

    try:
        store.create_task("owner", "single", {}, task_id="task")
        claimed = store.claim_next_task("test-runner")
        result = TaskRunner(store, handler).run_claimed_task(claimed)
        assert result["status"] == "cancelled"
        assert secret not in result["message"]
        assert "[REDACTED]" in result["message"]
        assert len(result["message"]) <= 2_000
    finally:
        store.close()


def test_old_runner_quietly_returns_current_snapshot_after_reclaim(tmp_path):
    now = [1_000.0]
    store = TaskStore(tmp_path / "tasks.db", clock=lambda: now[0])
    called = False

    def old_handler(snapshot, cancel_check, progress):
        nonlocal called
        called = True
        return {"worker": "old"}

    try:
        store.create_task("owner", "single", {}, task_id="task")
        old_claim = store.claim_next_task("runner-old")
        now[0] += 100
        store.recover_stale_tasks(stale_after_seconds=50)
        new_claim = store.claim_next_task("runner-new")

        observed = TaskRunner(store, old_handler, runner_id="runner-old").run_claimed_task(old_claim)
        assert called is False
        assert observed["status"] == "analyzing"
        assert observed["attempt_count"] == new_claim["attempt_count"]

        completed = store.complete_task(
            "owner", "task", {"worker": "new"}, expected_attempt=new_claim["attempt_count"]
        )
        assert completed["result"] == {"worker": "new"}
    finally:
        store.close()


def test_start_is_idempotent_and_stop_joins_bounded_dispatcher(tmp_path):
    store = _store(tmp_path)
    handled = threading.Event()

    def handler(snapshot, cancel_check, progress):
        handled.set()
        return {"ok": True}

    runner = TaskRunner(store, handler, max_workers=1, poll_interval=0.01)
    try:
        store.create_task("owner", "single", {}, task_id="task")
        assert runner.start() is True
        assert runner.start() is False
        runner.wake()
        assert handled.wait(1)
        assert runner.stop() is True
        assert runner.stop() is False
        assert store.get_task("owner", "task")["status"] == "completed"
    finally:
        runner.stop()
        store.close()


def test_stop_without_wait_blocks_restart_until_old_generation_finishes(tmp_path):
    store = _store(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def handler(snapshot, cancel_check, progress):
        entered.set()
        assert release.wait(2)
        return {"generation": "old"}

    runner = TaskRunner(store, handler, max_workers=1, poll_interval=0.01)
    try:
        store.create_task("owner", "single", {}, task_id="task")
        assert runner.start() is True
        assert entered.wait(1)
        assert runner.stop(wait=False) is True
        assert runner.start() is False
    finally:
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = store.get_task("owner", "task")
            if snapshot is not None and snapshot["status"] == "completed":
                break
            time.sleep(0.01)
        runner.stop()
        store.close()


def test_future_exception_is_observed_and_reported(tmp_path):
    store = _store(tmp_path)
    reported = []
    error_seen = threading.Event()

    def report_error(error):
        reported.append(error)
        error_seen.set()

    runner = TaskRunner(
        store,
        lambda snapshot, cancel_check, progress: {},
        poll_interval=0.01,
        error_handler=report_error,
    )

    def crash_worker(snapshot):
        raise RuntimeError("future exploded")

    runner.run_claimed_task = crash_worker
    try:
        store.create_task("owner", "single", {}, task_id="task")
        runner.start()
        assert error_seen.wait(1)
        assert isinstance(reported[0], RuntimeError)
        assert str(reported[0]) == "future exploded"
        snapshot = store.get_task("owner", "task")
        assert snapshot["status"] == "failed"
        assert snapshot["error_code"] == "runner_worker_crash"
        assert snapshot["retryable"] is True
    finally:
        runner.stop()
        store.close()


def test_dispatcher_survives_transient_claim_error(tmp_path):
    store = _store(tmp_path)
    errors = []
    handled = threading.Event()
    original_claim = store.claim_next_task
    claim_calls = 0

    def flaky_claim(runner_id):
        nonlocal claim_calls
        claim_calls += 1
        if claim_calls == 1:
            raise RuntimeError("temporary claim failure")
        return original_claim(runner_id)

    def handler(snapshot, cancel_check, progress):
        handled.set()
        return {"ok": True}

    store.claim_next_task = flaky_claim
    runner = TaskRunner(
        store,
        handler,
        poll_interval=0.01,
        error_handler=errors.append,
    )
    try:
        store.create_task("owner", "single", {}, task_id="task")
        runner.start()
        assert handled.wait(1)
        completed = _wait_for_status(store, "owner", "task", "completed")
        assert [str(error) for error in errors] == ["temporary claim failure"]
        assert completed["status"] == "completed"
    finally:
        runner.stop()
        store.close()


def test_dispatcher_survives_submit_error_and_fails_claimed_attempt(tmp_path, monkeypatch):
    class FailOnceExecutor:
        def __init__(self, *args, **kwargs):
            self.inner = RealThreadPoolExecutor(*args, **kwargs)
            self.failed = False

        def submit(self, fn, *args, **kwargs):
            if not self.failed:
                self.failed = True
                raise RuntimeError("temporary submit failure")
            return self.inner.submit(fn, *args, **kwargs)

        def shutdown(self, wait=True):
            self.inner.shutdown(wait=wait)

    monkeypatch.setattr(task_runner_module, "ThreadPoolExecutor", FailOnceExecutor)
    store = _store(tmp_path)
    errors = []
    handled = threading.Event()

    def handler(snapshot, cancel_check, progress):
        handled.set()
        return {"ok": True}

    runner = TaskRunner(store, handler, poll_interval=0.01, error_handler=errors.append)
    try:
        store.create_task("owner", "single", {}, task_id="submit-failed")
        store.create_task("owner", "single", {}, task_id="next-task")
        runner.start()
        assert handled.wait(1)
        completed = _wait_for_status(store, "owner", "next-task", "completed")
        failed = store.get_task("owner", "submit-failed")
        assert failed["status"] == "failed"
        assert failed["error_code"] == "runner_submit_error"
        assert completed["status"] == "completed"
        assert [str(error) for error in errors] == ["temporary submit failure"]
    finally:
        runner.stop()
        store.close()
