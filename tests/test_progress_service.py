"""Tests for ProgressStateService (extracted to services/progress.py)."""

import re
import time
from threading import Lock

import pytest

from services.progress import ProgressStateService


def _make_service():
    return ProgressStateService(
        batch_state_map={},
        batch_lock_obj=Lock(),
        single_state_map={},
        single_lock_obj=Lock(),
        owner_pattern=re.compile(r"[^A-Za-z0-9._-]"),
        owner_max_len=120,
        max_tasks_per_owner=10,
    )


class TestSingleProgress:
    def test_update_then_snapshot(self):
        svc = _make_service()
        svc.update_single("owner1", "task1", status="running", stage="asr")
        snap = svc.get_single_snapshot("owner1", "task1")
        assert snap["status"] == "running"
        assert snap["stage"] == "asr"
        assert snap["task_id"] == "task1"

    def test_missing_task_returns_idle_default(self):
        svc = _make_service()
        snap = svc.get_single_snapshot("owner1", "nope")
        assert snap["status"] == "idle"
        assert snap["task_id"] == "nope"

    def test_empty_owner_returns_default(self):
        svc = _make_service()
        snap = svc.get_single_snapshot("", "task1")
        assert snap["status"] == "idle"

    def test_update_with_empty_owner_is_noop(self):
        svc = _make_service()
        svc.update_single("", "task1", status="running")
        # nothing stored under empty owner
        assert svc.single_state_map == {}


class TestBatchProgress:
    def test_update_then_snapshot(self):
        svc = _make_service()
        svc.update_batch("owner1", "b1", total=3, current=1, status="running")
        snap = svc.get_batch_snapshot("owner1", "b1")
        assert snap["total"] == 3
        assert snap["current"] == 1
        assert snap["status"] == "running"

    def test_latest_selected_when_no_task_id(self):
        svc = _make_service()
        svc.update_batch("owner1", "b1", status="completed")
        time.sleep(0.01)  # ensure distinct updated_at_ts
        svc.update_batch("owner1", "b2", status="running")
        snap = svc.get_batch_snapshot("owner1")
        # b2 updated last -> selected
        assert snap["task_id"] == "b2"
        assert snap["status"] == "running"


class TestTrimming:
    def test_trims_to_max_tasks_per_owner(self):
        svc = _make_service()  # max 10
        for i in range(15):
            svc.update_single("owner1", f"task{i}", status="running")
        assert len(svc.single_state_map["owner1"]) <= 10


class TestTaskIdNormalization:
    def test_resolve_generates_id_when_blank(self):
        svc = _make_service()
        generated = svc.resolve_task_id("")
        assert generated and len(generated) >= 16

    def test_resolve_sanitizes_unsafe_chars(self):
        svc = _make_service()
        resolved = svc.resolve_task_id("a/b c..d")
        assert "/" not in resolved and " " not in resolved
