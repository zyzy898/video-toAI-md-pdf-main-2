"""Progress tracking service.

Tracks per-owner, per-task progress for single and batch analysis runs.
State maps and locks are injected by the caller so the service holds no
module-level global state of its own.
"""

import re
import time
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Tuple
from uuid import uuid4


class ProgressStateService:
    DEFAULT_BATCH_STATE: Dict[str, Any] = {
        "task_id": "",
        "total": 0,
        "current": 0,
        "status": "idle",
        "current_file": "",
        "stage": "idle",
        "message": "",
        "updated_at": "",
        "updated_at_ts": 0.0,
    }
    DEFAULT_SINGLE_STATE: Dict[str, Any] = {
        "task_id": "",
        "status": "idle",
        "current_file": "",
        "stage": "idle",
        "message": "",
        "updated_at": "",
        "updated_at_ts": 0.0,
    }

    def __init__(
        self,
        batch_state_map: Dict[str, Dict[str, Dict[str, Any]]],
        batch_lock_obj: Lock,
        single_state_map: Dict[str, Dict[str, Dict[str, Any]]],
        single_lock_obj: Lock,
        owner_pattern: re.Pattern[str],
        owner_max_len: int,
        max_tasks_per_owner: int = 100,
    ):
        self.batch_state_map = batch_state_map
        self.batch_lock = batch_lock_obj
        self.single_state_map = single_state_map
        self.single_lock = single_lock_obj
        self.owner_pattern = owner_pattern
        self.owner_max_len = max(1, int(owner_max_len))
        self.task_pattern = re.compile(r"[^A-Za-z0-9._-]")
        self.max_tasks_per_owner = max(10, min(500, int(max_tasks_per_owner)))

    def _normalize_owner(self, raw_owner: Any) -> str:
        owner = str(raw_owner or "").strip()
        if not owner:
            return ""
        owner = self.owner_pattern.sub("", owner)
        if len(owner) > self.owner_max_len:
            owner = owner[: self.owner_max_len]
        return owner

    def _normalize_task_id(self, raw_task_id: Any) -> str:
        task_id = str(raw_task_id or "").strip()
        if not task_id:
            return ""
        task_id = self.task_pattern.sub("", task_id)
        if len(task_id) > 120:
            task_id = task_id[:120]
        return task_id

    def resolve_task_id(self, raw_task_id: Any) -> str:
        task_id = self._normalize_task_id(raw_task_id)
        return task_id or uuid4().hex

    def _new_batch_state(self) -> Dict[str, Any]:
        return dict(self.DEFAULT_BATCH_STATE)

    def _new_single_state(self) -> Dict[str, Any]:
        return dict(self.DEFAULT_SINGLE_STATE)

    def _trim_owner_tasks(self, owner_tasks: Dict[str, Dict[str, Any]]) -> None:
        if len(owner_tasks) <= self.max_tasks_per_owner:
            return

        def _sort_key(item: Tuple[str, Dict[str, Any]]) -> float:
            state = item[1]
            try:
                return float(state.get("updated_at_ts", 0.0))
            except (TypeError, ValueError):
                return 0.0

        sorted_items = sorted(owner_tasks.items(), key=_sort_key, reverse=True)
        owner_tasks.clear()
        for task_id, state in sorted_items[: self.max_tasks_per_owner]:
            owner_tasks[task_id] = state

    def _select_latest_state(
        self,
        owner_tasks: Dict[str, Dict[str, Any]],
        default_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not owner_tasks:
            return default_state

        def _state_ts(state: Dict[str, Any]) -> float:
            try:
                return float(state.get("updated_at_ts", 0.0))
            except (TypeError, ValueError):
                return 0.0

        latest = max(owner_tasks.values(), key=_state_ts)
        payload = dict(default_state)
        payload.update(latest)
        return payload

    def update_batch(self, owner_id: str, task_id: str, **kwargs: Any) -> None:
        owner = self._normalize_owner(owner_id)
        if not owner:
            return
        normalized_task_id = self.resolve_task_id(task_id)
        with self.batch_lock:
            owner_tasks = self.batch_state_map.setdefault(owner, {})
            state = owner_tasks.setdefault(normalized_task_id, self._new_batch_state())
            state.update(kwargs)
            state["task_id"] = normalized_task_id
            state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state["updated_at_ts"] = time.time()
            owner_tasks[normalized_task_id] = state
            self._trim_owner_tasks(owner_tasks)

    def update_single(self, owner_id: str, task_id: str, **kwargs: Any) -> None:
        owner = self._normalize_owner(owner_id)
        if not owner:
            return
        normalized_task_id = self.resolve_task_id(task_id)
        with self.single_lock:
            owner_tasks = self.single_state_map.setdefault(owner, {})
            state = owner_tasks.setdefault(normalized_task_id, self._new_single_state())
            state.update(kwargs)
            state["task_id"] = normalized_task_id
            state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state["updated_at_ts"] = time.time()
            owner_tasks[normalized_task_id] = state
            self._trim_owner_tasks(owner_tasks)

    def get_batch_snapshot(self, owner_id: str, task_id: str = "") -> Dict[str, Any]:
        owner = self._normalize_owner(owner_id)
        requested_task_id = self._normalize_task_id(task_id)
        if not owner:
            payload = self._new_batch_state()
            payload["task_id"] = requested_task_id
            return payload
        with self.batch_lock:
            owner_tasks = self.batch_state_map.get(owner, {})
            if requested_task_id:
                state = owner_tasks.get(requested_task_id)
                payload = self._new_batch_state()
                if state is None:
                    payload["task_id"] = requested_task_id
                    return payload
                payload.update(state)
                return payload
            return self._select_latest_state(owner_tasks, self._new_batch_state())

    def get_single_snapshot(self, owner_id: str, task_id: str = "") -> Dict[str, Any]:
        owner = self._normalize_owner(owner_id)
        requested_task_id = self._normalize_task_id(task_id)
        if not owner:
            payload = self._new_single_state()
            payload["task_id"] = requested_task_id
            return payload
        with self.single_lock:
            owner_tasks = self.single_state_map.get(owner, {})
            if requested_task_id:
                state = owner_tasks.get(requested_task_id)
                payload = self._new_single_state()
                if state is None:
                    payload["task_id"] = requested_task_id
                    return payload
                payload.update(state)
                return payload
            return self._select_latest_state(owner_tasks, self._new_single_state())
