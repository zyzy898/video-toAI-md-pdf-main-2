"""Bounded background runner for durable tasks."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from typing import Any, Callable, Mapping
from uuid import uuid4

from services.task_store import TaskLeaseLostError, TaskStore


LOGGER = logging.getLogger(__name__)


class TaskCancelledError(RuntimeError):
    """Raised by cooperative handlers when work should stop."""


class TaskRunner:
    def __init__(
        self,
        store: TaskStore,
        handler: Callable[[dict[str, Any], Callable[[], bool], Callable[..., dict[str, Any]]], Any],
        *,
        max_workers: int = 2,
        poll_interval: float = 0.25,
        stale_after_seconds: float = 300,
        runner_id: str | None = None,
        error_handler: Callable[[BaseException], None] | None = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.store = store
        self.handler = handler
        self.max_workers = int(max_workers)
        self.poll_interval = max(0.01, float(poll_interval))
        self.stale_after_seconds = float(stale_after_seconds)
        self._heartbeat_interval = max(0.01, self.stale_after_seconds / 3)
        self.runner_id = runner_id or uuid4().hex
        self.error_handler = error_handler
        self._lifecycle_lock = threading.Lock()
        self._lock = threading.RLock()
        self._state = "stopped"
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._dispatcher: threading.Thread | None = None
        self._futures: set[Future[Any]] = set()
        self._future_claims: dict[Future[Any], tuple[str, str, int]] = {}
        self._heartbeat_stop_events: set[threading.Event] = set()

    def start(self) -> bool:
        with self._lifecycle_lock:
            with self._lock:
                self._finish_stop_locked()
                if self._state != "stopped":
                    return False
                self.store.recover_stale_tasks(self.stale_after_seconds)
                self._stop_event.clear()
                self._wake_event.clear()
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers, thread_name_prefix=f"task-{self.runner_id[:8]}"
                )
                self._dispatcher = threading.Thread(
                    target=self._dispatch_loop, name=f"task-dispatch-{self.runner_id[:8]}", daemon=True
                )
                self._state = "running"
                self._dispatcher.start()
                return True

    def stop(self, wait: bool = True) -> bool:
        with self._lifecycle_lock:
            with self._lock:
                self._finish_stop_locked()
                for heartbeat_stop in tuple(self._heartbeat_stop_events):
                    heartbeat_stop.set()
                if self._state == "stopped":
                    return False
                self._state = "stopping"
                dispatcher = self._dispatcher
                executor = self._executor
                self._stop_event.set()
                self._wake_event.set()
            if dispatcher is not None and dispatcher is not threading.current_thread():
                dispatcher.join(timeout=None if wait else 0)
            if executor is not None:
                executor.shutdown(wait=wait)
            with self._lock:
                if wait:
                    self._futures.clear()
                    self._future_claims.clear()
                    self._dispatcher = None
                    self._executor = None
                    self._state = "stopped"
                else:
                    self._finish_stop_locked()
            return True

    def wake(self) -> None:
        self._wake_event.set()

    def poll_once(self, *, run_inline: bool = False) -> bool:
        """Claim one task; inline mode is deterministic for tests."""
        with self._lock:
            if not run_inline:
                if self._executor is None or self._state != "running":
                    raise RuntimeError("TaskRunner must be started before asynchronous polling")
                if len(self._futures) >= self.max_workers:
                    return False
            claimed = self.store.claim_next_task(self.runner_id)
            if claimed is None:
                return False
            if run_inline:
                self.run_claimed_task(claimed)
                return True
            try:
                future = self._executor.submit(self.run_claimed_task, claimed)
            except Exception:
                try:
                    self.store.fail_task(
                        claimed["owner_id"],
                        claimed["task_id"],
                        error_code="runner_submit_error",
                        error_message="Task runner could not submit claimed work",
                        retryable=True,
                        expected_attempt=claimed["attempt_count"],
                    )
                except TaskLeaseLostError:
                    pass
                raise
            self._futures.add(future)
            self._future_claims[future] = (
                claimed["owner_id"],
                claimed["task_id"],
                claimed["attempt_count"],
            )
            future.add_done_callback(self._task_finished)
            return True

    def _task_finished(self, future: Future[Any]) -> None:
        try:
            error = future.exception()
        except CancelledError as exc:
            error = exc
        with self._lock:
            claim = self._future_claims.get(future)
        if error is not None and claim is not None:
            owner_id, task_id, expected_attempt = claim
            try:
                self.store.fail_task(
                    owner_id,
                    task_id,
                    error_code="runner_worker_crash",
                    error_message=f"Task worker crashed: {type(error).__name__}",
                    retryable=True,
                    expected_attempt=expected_attempt,
                )
            except TaskLeaseLostError:
                pass
            except Exception as persist_error:
                self._report_background_error(persist_error)
        if error is not None:
            self._report_background_error(error)
        with self._lock:
            self._futures.discard(future)
            self._future_claims.pop(future, None)
            self._finish_stop_locked()
        self.wake()

    def _report_background_error(self, error: BaseException) -> None:
        if self.error_handler is None:
            LOGGER.error("Task runner background error: %s", type(error).__name__)
            return
        try:
            self.error_handler(error)
        except Exception:
            LOGGER.error("Task runner error handler failed")

    def _finish_stop_locked(self) -> None:
        if self._state != "stopping":
            return
        dispatcher = self._dispatcher
        if dispatcher is threading.current_thread() or (
            dispatcher is not None and not dispatcher.is_alive()
        ):
            self._dispatcher = None
        if self._dispatcher is None and not self._futures:
            self._executor = None
            self._state = "stopped"

    def _dispatch_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                scheduled = False
                while not self._stop_event.is_set():
                    with self._lock:
                        capacity = self.max_workers - len(self._futures)
                    if capacity <= 0:
                        break
                    try:
                        polled = self.poll_once()
                    except Exception as exc:
                        self._report_background_error(exc)
                        break
                    if not polled:
                        break
                    scheduled = True
                if scheduled:
                    continue
                self._wake_event.wait(self.poll_interval)
                self._wake_event.clear()
        finally:
            with self._lock:
                self._finish_stop_locked()

    def _start_lease_heartbeat(
        self,
        owner_id: str,
        task_id: str,
        expected_attempt: int,
    ) -> tuple[threading.Event, threading.Thread]:
        stop_event = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(owner_id, task_id, expected_attempt, stop_event),
            name=f"task-heartbeat-{self.runner_id[:8]}-{task_id[:8]}",
            daemon=True,
        )
        with self._lock:
            self._heartbeat_stop_events.add(stop_event)
            if self._stop_event.is_set():
                stop_event.set()
        try:
            heartbeat.start()
        except Exception:
            with self._lock:
                self._heartbeat_stop_events.discard(stop_event)
            raise
        return stop_event, heartbeat

    def _heartbeat_loop(
        self,
        owner_id: str,
        task_id: str,
        expected_attempt: int,
        stop_event: threading.Event,
    ) -> None:
        while not stop_event.wait(self._heartbeat_interval):
            try:
                self.store.update_progress(
                    owner_id,
                    task_id,
                    expected_attempt=expected_attempt,
                )
            except TaskLeaseLostError:
                return
            except Exception as exc:
                self._report_background_error(exc)

    def _stop_lease_heartbeat(
        self,
        stop_event: threading.Event,
        heartbeat: threading.Thread,
    ) -> None:
        stop_event.set()
        if heartbeat is not threading.current_thread():
            heartbeat.join()
        with self._lock:
            self._heartbeat_stop_events.discard(stop_event)

    def run_claimed_task(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        owner_id = snapshot["owner_id"]
        task_id = snapshot["task_id"]
        expected_attempt = snapshot["attempt_count"]

        def current_snapshot() -> dict[str, Any]:
            return self.store.get_task(owner_id, task_id) or snapshot

        def cancel_check() -> bool:
            current = self.store.get_task(owner_id, task_id)
            if current is None or current["attempt_count"] != expected_attempt:
                raise TaskLeaseLostError("Task lease was superseded")
            if current["cancel_requested"] or current["status"] == "cancelled":
                raise TaskCancelledError("Task cancellation requested")
            if current["status"] != "analyzing":
                raise TaskLeaseLostError("Task lease is no longer active")
            self.store.update_progress(owner_id, task_id, expected_attempt=expected_attempt)
            return False

        def progress(update: Mapping[str, Any] | None = None, **changes: Any) -> dict[str, Any]:
            if update is not None:
                changes = {**dict(update), **changes}
            cancel_check()
            return self.store.update_progress(
                owner_id, task_id, expected_attempt=expected_attempt, **changes
            )

        heartbeat: tuple[threading.Event, threading.Thread] | None = None
        try:
            cancel_check()
            heartbeat = self._start_lease_heartbeat(owner_id, task_id, expected_attempt)
            result = self.handler(snapshot, cancel_check, progress)
            return self.store.complete_task(
                owner_id, task_id, result, expected_attempt=expected_attempt
            )
        except TaskLeaseLostError:
            return current_snapshot()
        except TaskCancelledError as exc:
            try:
                return self.store.confirm_cancelled(
                    owner_id,
                    task_id,
                    str(exc) or "Task cancelled",
                    expected_attempt=expected_attempt,
                )
            except TaskLeaseLostError:
                return current_snapshot()
        except Exception as exc:
            try:
                return self.store.fail_task(
                    owner_id,
                    task_id,
                    error_code=str(getattr(exc, "code", type(exc).__name__)),
                    error_message=str(exc) or type(exc).__name__,
                    error_http_status=getattr(exc, "http_status", getattr(exc, "status_code", None)),
                    retryable=bool(getattr(exc, "retryable", False)),
                    expected_attempt=expected_attempt,
                )
            except TaskLeaseLostError:
                return current_snapshot()
        finally:
            if heartbeat is not None:
                self._stop_lease_heartbeat(*heartbeat)
