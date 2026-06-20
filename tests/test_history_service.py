"""Tests for HistoryService (extracted to services/history.py)."""

import re
from threading import RLock

import pytest

from services.history import HistoryService


def _make_service(tmp_path, max_history=3):
    return HistoryService(
        history_path=tmp_path / "history.json",
        lock_obj=RLock(),
        max_history=max_history,
        owner_pattern=re.compile(r"[^A-Za-z0-9._-]"),
        owner_max_len=120,
        owner_header="X-Client-ID",
        owner_cookie="video_insights_client_id",
        owner_cookie_max_age=1000,
    )


class TestOwnerNormalization:
    def test_strips_unsafe_chars(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.normalize_owner("a/b c!") == "abc"

    def test_truncates_to_max_len(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.owner_max_len = 5
        assert svc.normalize_owner("abcdefghij") == "abcde"

    def test_empty_returns_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.normalize_owner("") == ""


class TestSaveLoadIsolation:
    def test_save_then_load_for_owner(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save({"id": "1", "title": "a"}, "owner1")
        records = svc.load("owner1")
        assert len(records) == 1
        assert records[0]["id"] == "1"

    def test_owners_isolated(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save({"id": "1"}, "owner1")
        svc.save({"id": "2"}, "owner2")
        assert len(svc.load("owner1")) == 1
        assert len(svc.load("owner2")) == 1
        assert svc.load("owner1")[0]["id"] == "1"

    def test_empty_owner_save_is_noop(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save({"id": "1"}, "")
        assert svc.load("owner1") == []


class TestTrimAndDelete:
    def test_trims_per_owner(self, tmp_path):
        svc = _make_service(tmp_path, max_history=3)
        for i in range(5):
            svc.save({"id": str(i)}, "owner1")
        assert len(svc.load("owner1")) == 3

    def test_delete_removes_only_matching(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save({"id": "1"}, "owner1")
        svc.save({"id": "2"}, "owner1")
        svc.delete("1", "owner1")
        remaining = [r["id"] for r in svc.load("owner1")]
        assert remaining == ["2"]

    def test_delete_wrong_owner_is_noop(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.save({"id": "1"}, "owner1")
        svc.delete("1", "owner2")
        assert len(svc.load("owner1")) == 1


class TestStripOwnerField:
    def test_removes_owner_id(self, tmp_path):
        svc = _make_service(tmp_path)
        stripped = svc.strip_owner_field({"id": "1", "owner_id": "x"})
        assert "owner_id" not in stripped
        assert stripped["id"] == "1"
