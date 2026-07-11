"""Durable task state backed by SQLite."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4


KINDS = {"single", "batch", "url"}
STATUSES = {"uploading", "queued", "analyzing", "completed", "failed", "cancelled"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class TaskStoreError(RuntimeError):
    """Base task persistence error."""


class TaskConflictError(TaskStoreError):
    """The same identity was reused for a different request."""


class TaskStateError(TaskStoreError):
    """A task operation is invalid for its current state."""


class TaskLeaseLostError(TaskStateError):
    """A worker attempted to write through an expired task attempt."""


class TaskNotFoundError(TaskStoreError):
    """A task does not exist for the supplied owner."""


class TaskSerializationError(TaskStoreError):
    """Task request or result data is not JSON serializable."""


class TaskStore:
    """Thread-safe SQLite task repository with atomic worker claims."""

    MAX_ERROR_MESSAGE_LENGTH = 2_000
    _SENSITIVE_PARTS = (
        "apikey",
        "authorization",
        "cookie",
        "credential",
        "password",
        "privatekey",
        "secret",
        "token",
    )
    _SENSITIVE_ASSIGNMENT = re.compile(
        r"""
        (?P<key>[\"']?(?:api[_-]?key|token|authorization|password|secret)[\"']?)
        (?P<separator>\s*[:=]\s*)
        (?:(?P<quote>[\"'])(?P<quoted>.*?)(?P=quote)|(?P<bare>(?:Bearer\s+)?[^\s&,;]+))
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = 5_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database_path = str(database_path)
        self._clock = clock
        self._lock = threading.RLock()
        self._closed = False
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database_path,
            timeout=max(0, busy_timeout_ms) / 1000,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(f"PRAGMA busy_timeout = {max(0, int(busy_timeout_ms))}")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            self._closed = True
            raise

    def _initialize(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    owner_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    percent REAL NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    current INTEGER NOT NULL DEFAULT 0,
                    current_file TEXT NOT NULL DEFAULT '',
                    file_progress_json TEXT NOT NULL DEFAULT '[]',
                    request_json TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    error_http_status INTEGER,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    recovery_count INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT,
                    claimed_by TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    heartbeat_at REAL,
                    PRIMARY KEY (owner_id, task_id),
                    CHECK (kind IN ('single', 'batch', 'url')),
                    CHECK (status IN ('uploading', 'queued', 'analyzing', 'completed', 'failed', 'cancelled'))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS tasks_owner_idempotency
                    ON tasks(owner_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS tasks_queue
                    ON tasks(status, created_at, task_id);
                CREATE INDEX IF NOT EXISTS tasks_owner_created
                    ON tasks(owner_id, created_at DESC);
                """
            )
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                columns = {
                    str(row[1])
                    for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
                }
                if "file_progress_json" not in columns:
                    self._connection.execute(
                        "ALTER TABLE tasks ADD COLUMN file_progress_json TEXT NOT NULL DEFAULT '[]'"
                    )
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._ensure_open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def _ensure_open(self) -> None:
        if self._closed:
            raise TaskStoreError("TaskStore is closed")

    @staticmethod
    def _json(value: Any, label: str) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise TaskSerializationError(f"{label} is not JSON serializable") from exc

    @classmethod
    def _public_request(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            public: dict[str, Any] = {}
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if any(part in normalized for part in cls._SENSITIVE_PARTS):
                    continue
                public[str(key)] = cls._public_request(item)
            return public
        if isinstance(value, list):
            return [cls._public_request(item) for item in value]
        return value

    @classmethod
    def _safe_error_message(cls, value: Any) -> str:
        message = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
        message = cls._SENSITIVE_ASSIGNMENT.sub(
            lambda match: f"{match.group('key')}{match.group('separator')}[REDACTED]",
            message,
        )
        return message[: cls.MAX_ERROR_MESSAGE_LENGTH]

    def _snapshot(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        request = json.loads(data.pop("request_json"))
        result_json = data.pop("result_json")
        file_progress_json = data.pop("file_progress_json", "[]")
        for internal in ("request_hash", "idempotency_key", "claimed_by"):
            data.pop(internal, None)
        data["request"] = self._public_request(request)
        data["result"] = json.loads(result_json) if result_json is not None else None
        file_progress = json.loads(file_progress_json or "[]")
        data["file_progress"] = file_progress if isinstance(file_progress, list) else []
        data["retryable"] = bool(data["retryable"])
        data["cancel_requested"] = bool(data["cancel_requested"])
        return data

    def _summary(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        request = json.loads(data.pop("request_json"))
        file_progress_json = data.pop("file_progress_json", "[]")
        data["request"] = self._public_request(request)
        file_progress = json.loads(file_progress_json or "[]")
        data["file_progress"] = file_progress if isinstance(file_progress, list) else []
        data["retryable"] = bool(data["retryable"])
        data["cancel_requested"] = bool(data["cancel_requested"])
        return data

    def _row(self, owner_id: str, task_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM tasks WHERE owner_id = ? AND task_id = ?", (owner_id, task_id)
        ).fetchone()

    @staticmethod
    def _identity(owner_id: str, task_id: str | None = None) -> tuple[str, str | None]:
        owner = str(owner_id or "").strip()
        if not owner:
            raise ValueError("owner_id is required")
        normalized_task = None if task_id is None else str(task_id).strip()
        if task_id is not None and not normalized_task:
            raise ValueError("task_id is required")
        return owner, normalized_task

    def create_task(
        self,
        owner_id: str,
        kind: str,
        request_payload: Any,
        task_id: str | None = None,
        status: str = "queued",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        owner, normalized_task = self._identity(owner_id, task_id)
        if kind not in KINDS:
            raise ValueError(f"unsupported task kind: {kind}")
        if status not in STATUSES:
            raise ValueError(f"unsupported task status: {status}")
        normalized_task = normalized_task or uuid4().hex
        request_json = self._json(request_payload, "request_payload")
        request_hash = hashlib.sha256(f"{kind}\0{request_json}".encode("utf-8")).hexdigest()
        key = str(idempotency_key).strip() if idempotency_key is not None else None
        key = key or None
        now = float(self._clock())
        started_at = now if status == "analyzing" else None
        finished_at = now if status in TERMINAL_STATUSES else None
        heartbeat_at = now if status == "analyzing" else None
        with self._transaction():
            existing = self._row(owner, normalized_task)
            if existing is None and key is not None:
                existing = self._connection.execute(
                    "SELECT * FROM tasks WHERE owner_id = ? AND idempotency_key = ?", (owner, key)
                ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise TaskConflictError("task identity already belongs to a different request")
                return self._snapshot(existing)  # type: ignore[return-value]
            self._connection.execute(
                """
                INSERT INTO tasks (
                    owner_id, task_id, kind, status, stage, request_json, request_hash,
                    idempotency_key, created_at, updated_at, started_at, finished_at,
                    heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner,
                    normalized_task,
                    kind,
                    status,
                    status,
                    request_json,
                    request_hash,
                    key,
                    now,
                    now,
                    started_at,
                    finished_at,
                    heartbeat_at,
                ),
            )
            return self._snapshot(self._row(owner, normalized_task))  # type: ignore[return-value]

    def get_task(self, owner_id: str, task_id: str) -> dict[str, Any] | None:
        owner, task = self._identity(owner_id, task_id)
        with self._lock:
            self._ensure_open()
            return self._snapshot(self._row(owner, task or ""))

    def latest_task(self, owner_id: str) -> dict[str, Any] | None:
        owner, _ = self._identity(owner_id)
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE owner_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1", (owner,)
            ).fetchone()
            return self._snapshot(row)

    def list_tasks(self, owner_id: str) -> list[dict[str, Any]]:
        owner, _ = self._identity(owner_id)
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT task_id, kind, status, stage, message, percent, total,
                    current, current_file, file_progress_json, request_json, error_code, error_message,
                    error_http_status, retryable, cancel_requested, attempt_count,
                    recovery_count, created_at, updated_at, started_at, finished_at
                FROM tasks
                WHERE owner_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (owner,),
            ).fetchall()
            return [self._summary(row) for row in rows]

    def claim_next_task(self, runner_id: str) -> dict[str, Any] | None:
        runner = str(runner_id or "").strip()
        if not runner:
            raise ValueError("runner_id is required")
        now = float(self._clock())
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._connection.execute(
                """
                UPDATE tasks SET status = 'analyzing', stage = 'analyzing', claimed_by = ?,
                    attempt_count = attempt_count + 1, revision = revision + 1,
                    started_at = ?, finished_at = NULL, heartbeat_at = ?, updated_at = ?
                WHERE owner_id = ? AND task_id = ? AND status = 'queued'
                """,
                (runner, now, now, now, row["owner_id"], row["task_id"]),
            )
            return self._snapshot(self._row(row["owner_id"], row["task_id"]))

    def update_progress(
        self,
        owner_id: str,
        task_id: str,
        *,
        stage: str | None = None,
        message: str | None = None,
        percent: float | None = None,
        total: int | None = None,
        current: int | None = None,
        current_file: str | None = None,
        file_progress: list[dict[str, Any]] | None = None,
        status: str | None = None,
        expected_attempt: int | None = None,
    ) -> dict[str, Any]:
        owner, task = self._identity(owner_id, task_id)
        if percent is not None and not 0 <= float(percent) <= 100:
            raise ValueError("percent must be between 0 and 100")
        if total is not None and int(total) < 0:
            raise ValueError("total must be non-negative")
        if current is not None and int(current) < 0:
            raise ValueError("current must be non-negative")
        if file_progress is not None and not isinstance(file_progress, list):
            raise ValueError("file_progress must be a list")
        file_progress_json = (
            None if file_progress is None else self._json(file_progress, "file_progress")
        )
        now = float(self._clock())
        with self._transaction():
            row = self._require_row(owner, task or "")
            self._check_attempt(row, expected_attempt)
            old_status = row["status"]
            new_status = status or old_status
            if old_status in TERMINAL_STATUSES:
                raise TaskStateError(f"cannot update terminal task in state {old_status}")
            if new_status not in STATUSES or (new_status != old_status and (old_status, new_status) != ("uploading", "queued")):
                raise TaskStateError(f"cannot transition task from {old_status} to {new_status}")
            values = {
                "status": new_status,
                "stage": row["stage"] if stage is None else str(stage),
                "message": row["message"] if message is None else str(message),
                "percent": row["percent"] if percent is None else float(percent),
                "total": row["total"] if total is None else int(total),
                "current": (
                    row["current"]
                    if current is None
                    else max(int(row["current"]), int(current))
                    if row["kind"] == "batch"
                    else int(current)
                ),
                "current_file": row["current_file"] if current_file is None else str(current_file),
                "file_progress_json": (
                    row["file_progress_json"]
                    if file_progress_json is None
                    else file_progress_json
                ),
            }
            self._connection.execute(
                """
                UPDATE tasks SET status = :status, stage = :stage, message = :message,
                    percent = :percent, total = :total, current = :current,
                    current_file = :current_file, file_progress_json = :file_progress_json,
                    heartbeat_at = CASE WHEN :status = 'analyzing' THEN :now ELSE heartbeat_at END,
                    updated_at = :now, revision = revision + 1
                WHERE owner_id = :owner_id AND task_id = :task_id
                """,
                {**values, "now": now, "owner_id": owner, "task_id": task},
            )
            return self._snapshot(self._row(owner, task or ""))  # type: ignore[return-value]

    def complete_task(
        self,
        owner_id: str,
        task_id: str,
        result: Any,
        *,
        expected_attempt: int | None = None,
    ) -> dict[str, Any]:
        owner, task = self._identity(owner_id, task_id)
        result_json = self._json(result, "result")
        now = float(self._clock())
        with self._transaction():
            row = self._require_row(owner, task or "")
            self._check_attempt(row, expected_attempt)
            if row["status"] == "cancelled":
                return self._snapshot(row)  # type: ignore[return-value]
            if row["status"] == "completed":
                return self._snapshot(row)  # type: ignore[return-value]
            if row["status"] != "analyzing":
                raise TaskStateError(f"cannot complete task in state {row['status']}")
            cancelled = bool(row["cancel_requested"])
            self._connection.execute(
                """
                UPDATE tasks SET status = ?, stage = ?, message = ?, percent = ?,
                    result_json = ?, retryable = ?, finished_at = ?, heartbeat_at = ?,
                    updated_at = ?, revision = revision + 1
                WHERE owner_id = ? AND task_id = ?
                """,
                (
                    "cancelled" if cancelled else "completed",
                    "cancelled" if cancelled else "completed",
                    "Task cancelled" if cancelled else "Task completed",
                    row["percent"] if cancelled else 100,
                    None if cancelled else result_json,
                    1 if cancelled else 0,
                    now,
                    now,
                    now,
                    owner,
                    task,
                ),
            )
            return self._snapshot(self._row(owner, task or ""))  # type: ignore[return-value]

    def fail_task(
        self,
        owner_id: str,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        error_http_status: int | None = None,
        retryable: bool = False,
        expected_attempt: int | None = None,
    ) -> dict[str, Any]:
        owner, task = self._identity(owner_id, task_id)
        safe_error_message = self._safe_error_message(error_message)
        now = float(self._clock())
        with self._transaction():
            row = self._require_row(owner, task or "")
            self._check_attempt(row, expected_attempt)
            if row["status"] != "analyzing":
                raise TaskStateError(f"cannot fail task in state {row['status']}")
            cancelled = bool(row["cancel_requested"])
            self._connection.execute(
                """
                UPDATE tasks SET status = ?, stage = ?, message = ?, error_code = ?,
                    error_message = ?, error_http_status = ?, retryable = ?,
                    finished_at = ?, heartbeat_at = ?, updated_at = ?, revision = revision + 1
                WHERE owner_id = ? AND task_id = ?
                """,
                (
                    "cancelled" if cancelled else "failed",
                    "cancelled" if cancelled else "failed",
                    "Task cancelled" if cancelled else safe_error_message,
                    None if cancelled else str(error_code),
                    None if cancelled else safe_error_message,
                    None if cancelled else error_http_status,
                    1 if cancelled else int(bool(retryable)),
                    now,
                    now,
                    now,
                    owner,
                    task,
                ),
            )
            return self._snapshot(self._row(owner, task or ""))  # type: ignore[return-value]

    def request_cancel(self, owner_id: str, task_id: str) -> dict[str, Any]:
        owner, task = self._identity(owner_id, task_id)
        now = float(self._clock())
        with self._transaction():
            row = self._require_row(owner, task or "")
            if row["status"] in TERMINAL_STATUSES or row["cancel_requested"]:
                return self._snapshot(row)  # type: ignore[return-value]
            immediate = row["status"] in {"uploading", "queued"}
            self._connection.execute(
                """
                UPDATE tasks SET cancel_requested = 1, status = ?, stage = ?, message = ?,
                    retryable = ?, finished_at = ?, updated_at = ?, revision = revision + 1
                WHERE owner_id = ? AND task_id = ?
                """,
                (
                    "cancelled" if immediate else row["status"],
                    "cancelled" if immediate else row["stage"],
                    "Task cancelled" if immediate else "Cancellation requested",
                    1 if immediate else row["retryable"],
                    now if immediate else row["finished_at"],
                    now,
                    owner,
                    task,
                ),
            )
            return self._snapshot(self._row(owner, task or ""))  # type: ignore[return-value]

    def confirm_cancelled(
        self,
        owner_id: str,
        task_id: str,
        message: str = "Task cancelled",
        *,
        expected_attempt: int | None = None,
    ) -> dict[str, Any]:
        owner, task = self._identity(owner_id, task_id)
        safe_message = self._safe_error_message(message)
        now = float(self._clock())
        with self._transaction():
            row = self._require_row(owner, task or "")
            self._check_attempt(row, expected_attempt, allow_cancelled=True)
            if row["status"] == "cancelled":
                return self._snapshot(row)  # type: ignore[return-value]
            if row["status"] in {"completed", "failed"}:
                raise TaskStateError(f"cannot cancel task in state {row['status']}")
            self._connection.execute(
                """
                UPDATE tasks SET status = 'cancelled', stage = 'cancelled', message = ?,
                    cancel_requested = 1, retryable = 1, result_json = NULL,
                    finished_at = ?, heartbeat_at = ?, updated_at = ?, revision = revision + 1
                WHERE owner_id = ? AND task_id = ?
                """,
                (safe_message, now, now, now, owner, task),
            )
            return self._snapshot(self._row(owner, task or ""))  # type: ignore[return-value]

    def retry_task(self, owner_id: str, task_id: str) -> dict[str, Any]:
        owner, task = self._identity(owner_id, task_id)
        now = float(self._clock())
        with self._transaction():
            row = self._require_row(owner, task or "")
            if row["status"] not in {"failed", "cancelled"} or not row["retryable"]:
                raise TaskStateError("only retryable failed or cancelled tasks can be retried")
            self._connection.execute(
                """
                UPDATE tasks SET status = 'queued', stage = 'queued', message = 'Task queued for retry',
                    percent = 0, current = 0, current_file = '', file_progress_json = '[]',
                    result_json = NULL,
                    error_code = NULL, error_message = NULL, error_http_status = NULL,
                    retryable = 0, cancel_requested = 0, claimed_by = NULL,
                    started_at = NULL, finished_at = NULL, heartbeat_at = NULL,
                    updated_at = ?, revision = revision + 1
                WHERE owner_id = ? AND task_id = ?
                """,
                (now, owner, task),
            )
            return self._snapshot(self._row(owner, task or ""))  # type: ignore[return-value]

    def recover_stale_tasks(self, stale_after_seconds: float, now: float | None = None) -> int:
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds must be non-negative")
        current_time = float(self._clock() if now is None else now)
        cutoff = current_time - float(stale_after_seconds)
        with self._transaction():
            cancelled_cursor = self._connection.execute(
                """
                UPDATE tasks SET status = 'cancelled', stage = 'cancelled',
                    message = 'Task cancelled after stale runner lease', claimed_by = NULL,
                    retryable = 1, finished_at = ?, heartbeat_at = ?,
                    recovery_count = recovery_count + 1, updated_at = ?, revision = revision + 1
                WHERE status = 'analyzing' AND cancel_requested = 1
                    AND COALESCE(heartbeat_at, updated_at, started_at, created_at) <= ?
                """,
                (current_time, current_time, current_time, cutoff),
            )
            queued_cursor = self._connection.execute(
                """
                UPDATE tasks SET status = 'queued', stage = 'queued',
                    message = 'Recovered after stale runner lease', claimed_by = NULL,
                    percent = 0, current = 0, current_file = '', file_progress_json = '[]',
                    started_at = NULL, heartbeat_at = NULL, recovery_count = recovery_count + 1,
                    updated_at = ?, revision = revision + 1
                WHERE status = 'analyzing' AND cancel_requested = 0
                    AND COALESCE(heartbeat_at, updated_at, started_at, created_at) <= ?
                """,
                (current_time, cutoff),
            )
            return int(cancelled_cursor.rowcount + queued_cursor.rowcount)

    def list_queued(self, limit: int = 100, owner_id: str | None = None) -> list[dict[str, Any]]:
        safe_limit = max(0, int(limit))
        with self._lock:
            self._ensure_open()
            if owner_id is None:
                rows = self._connection.execute(
                    "SELECT * FROM tasks WHERE status = 'queued' ORDER BY created_at, rowid LIMIT ?", (safe_limit,)
                ).fetchall()
            else:
                owner, _ = self._identity(owner_id)
                rows = self._connection.execute(
                    """SELECT * FROM tasks WHERE status = 'queued' AND owner_id = ?
                    ORDER BY created_at, rowid LIMIT ?""",
                    (owner, safe_limit),
                ).fetchall()
            return [self._snapshot(row) for row in rows]  # type: ignore[misc]

    def _require_row(self, owner_id: str, task_id: str) -> sqlite3.Row:
        row = self._row(owner_id, task_id)
        if row is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        return row

    @staticmethod
    def _check_attempt(
        row: sqlite3.Row,
        expected_attempt: int | None,
        *,
        allow_cancelled: bool = False,
    ) -> None:
        if expected_attempt is None:
            return
        attempt_matches = row["attempt_count"] == int(expected_attempt)
        state_is_active = row["status"] == "analyzing" or (
            allow_cancelled and row["status"] == "cancelled"
        )
        if not attempt_matches or not state_is_active:
            raise TaskLeaseLostError(
                f"task attempt {expected_attempt} is no longer the active lease"
            )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> "TaskStore":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
