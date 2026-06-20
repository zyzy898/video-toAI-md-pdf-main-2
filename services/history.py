"""History persistence service.

Stores per-owner analysis history in a JSON file (atomic tmp+replace),
isolating records by a normalized owner id derived from request header/cookie.
Access is guarded by a caller-supplied lock.
"""

import json
import re
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List
from uuid import uuid4

from flask import g, request
import logging
import shutil
import time
from datetime import datetime
from threading import Lock, Thread
from typing import Tuple

from path_utils import _assert_within, _resolve_output_dir


class HistoryService:
    def __init__(
        self,
        history_path: Path,
        lock_obj: RLock,
        max_history: int,
        owner_pattern: re.Pattern[str],
        owner_max_len: int,
        owner_header: str,
        owner_cookie: str,
        owner_cookie_max_age: int,
    ):
        self.history_path = history_path
        self.lock = lock_obj
        self.max_history = max_history
        self.owner_pattern = owner_pattern
        self.owner_max_len = owner_max_len
        self.owner_header = owner_header
        self.owner_cookie = owner_cookie
        self.owner_cookie_max_age = owner_cookie_max_age

    def read_unlocked(self) -> List[Dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def write_unlocked(self, history: List[Dict[str, Any]]) -> None:
        tmp_path = self.history_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.history_path)

    def normalize_owner(self, raw_owner: Any) -> str:
        owner = str(raw_owner or "").strip()
        if not owner:
            return ""
        owner = self.owner_pattern.sub("", owner)
        if len(owner) > self.owner_max_len:
            owner = owner[: self.owner_max_len]
        return owner

    def extract_owner(self) -> str:
        from_header = self.normalize_owner(request.headers.get(self.owner_header))
        if from_header:
            return from_header
        from_cookie = self.normalize_owner(request.cookies.get(self.owner_cookie))
        if from_cookie:
            return from_cookie
        return ""

    def ensure_owner(self) -> str:
        owner = self.extract_owner()
        if owner:
            return owner
        owner = uuid4().hex
        g.history_owner_cookie = owner
        return owner

    def record_owner(self, record: Dict[str, Any]) -> str:
        return self.normalize_owner(record.get("owner_id"))

    def trim_history_per_owner(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        owner_counts: Dict[str, int] = {}
        trimmed: List[Dict[str, Any]] = []
        for record in history:
            owner = self.record_owner(record)
            if not owner:
                # Keep legacy records (no owner_id) to avoid accidental data loss.
                trimmed.append(record)
                continue
            count = owner_counts.get(owner, 0)
            if count >= self.max_history:
                continue
            owner_counts[owner] = count + 1
            trimmed.append(record)
        return trimmed

    def strip_owner_field(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload.pop("owner_id", None)
        return payload

    def load(self, owner_id: str) -> List[Dict[str, Any]]:
        owner = self.normalize_owner(owner_id)
        if not owner:
            return []
        with self.lock:
            history = self.read_unlocked()
            user_history = [item for item in history if self.record_owner(item) == owner]
            return user_history[: self.max_history]

    def save(self, record: Dict[str, Any], owner_id: str) -> None:
        owner = self.normalize_owner(owner_id)
        if not owner:
            return
        record_to_save = dict(record)
        record_to_save["owner_id"] = owner
        with self.lock:
            history = self.read_unlocked()
            history.insert(0, record_to_save)
            self.write_unlocked(self.trim_history_per_owner(history))

    def delete(self, record_id: str, owner_id: str) -> None:
        owner = self.normalize_owner(owner_id)
        if not owner:
            return
        with self.lock:
            history = self.read_unlocked()
            history = [
                r
                for r in history
                if not (str(r.get("id")) == str(record_id) and self.record_owner(r) == owner)
            ]
            self.write_unlocked(history)

    def attach_owner_cookie(self, response):
        pending_owner = self.normalize_owner(getattr(g, "history_owner_cookie", ""))
        if pending_owner:
            response.set_cookie(
                self.owner_cookie,
                pending_owner,
                max_age=self.owner_cookie_max_age,
                samesite="Lax",
                # 前端通过 localStorage + X-Client-ID 头管理身份，从不读取该 cookie，
                # 因此设为 HttpOnly 防止 XSS 窃取，不影响前端功能。
                httponly=True,
            )
        return response


class HistoryRetentionCleanupService:
    def __init__(
        self,
        history_service_obj: HistoryService,
        output_root: Path,
        ttl_seconds: int,
        scan_interval_seconds: int,
        logger_obj: logging.Logger,
    ):
        self.history_service = history_service_obj
        self.output_root = output_root
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.scan_interval_seconds = max(60, int(scan_interval_seconds))
        self.logger = logger_obj
        self._start_lock = Lock()
        self._started = False
        self._thread: Thread | None = None

    def _resolve_record_output_dir(self, record: Dict[str, Any]) -> Path | None:
        raw_output_dir = record.get("output_dir")
        if not raw_output_dir:
            return None
        try:
            output_dir = _resolve_output_dir(raw_output_dir, must_exist=False)
            _assert_within(output_dir, self.output_root, "output_dir")
            return output_dir
        except (ValueError, OSError):
            return None

    def _read_document_ts(self, output_dir: Path) -> float | None:
        try:
            resolved = output_dir.resolve(strict=False)
            _assert_within(resolved, self.output_root, "output_dir")
            md_path = resolved / "operation_guide.md"
            if not md_path.exists() or not md_path.is_file():
                return None
            return float(md_path.stat().st_mtime)
        except (ValueError, FileNotFoundError, OSError):
            return None

    def _parse_record_ts(self, record: Dict[str, Any]) -> float | None:
        timestamp_text = str(record.get("timestamp", "")).strip()
        if timestamp_text:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    return datetime.strptime(timestamp_text, fmt).timestamp()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(timestamp_text).timestamp()
            except ValueError:
                pass

        record_id = re.sub(r"\D+", "", str(record.get("id", "")).strip())
        if len(record_id) >= 14:
            try:
                return datetime.strptime(record_id[:14], "%Y%m%d%H%M%S").timestamp()
            except ValueError:
                return None
        return None

    def _record_reference_ts(self, record: Dict[str, Any], output_dir: Path | None) -> float | None:
        if output_dir is not None:
            doc_ts = self._read_document_ts(output_dir)
            if doc_ts is not None:
                return doc_ts
        return self._parse_record_ts(record)

    def _iter_output_dirs(self):
        if not self.output_root.exists():
            return
        for entry in self.output_root.iterdir():
            try:
                if entry.is_dir():
                    yield entry.resolve(strict=False)
            except OSError:
                continue

    def _delete_output_dir(self, output_dir: Path) -> bool:
        try:
            resolved = output_dir.resolve(strict=False)
            _assert_within(resolved, self.output_root, "output_dir")
            if not resolved.exists() or not resolved.is_dir():
                return False
            shutil.rmtree(resolved, ignore_errors=False)
            return True
        except (ValueError, FileNotFoundError, OSError):
            return False

    def cleanup_once(self) -> Tuple[int, int]:
        expire_before_ts = time.time() - float(self.ttl_seconds)
        removed_records = 0
        removed_output_dirs = 0

        retained_output_dirs: set[Path] = set()
        with self.history_service.lock:
            history = self.history_service.read_unlocked()
            retained_history: List[Dict[str, Any]] = []
            for record in history:
                output_dir = self._resolve_record_output_dir(record)
                reference_ts = self._record_reference_ts(record, output_dir)
                is_expired = reference_ts is not None and reference_ts <= expire_before_ts
                if is_expired:
                    removed_records += 1
                    continue
                retained_history.append(record)
                if output_dir is not None:
                    retained_output_dirs.add(output_dir.resolve(strict=False))

            if removed_records > 0:
                self.history_service.write_unlocked(retained_history)

        removable_dirs: set[Path] = set()
        for output_dir in self._iter_output_dirs():
            if output_dir in retained_output_dirs:
                continue
            doc_ts = self._read_document_ts(output_dir)
            if doc_ts is None or doc_ts > expire_before_ts:
                continue
            removable_dirs.add(output_dir)

        for output_dir in removable_dirs:
            if self._delete_output_dir(output_dir):
                removed_output_dirs += 1

        if removed_records > 0 or removed_output_dirs > 0:
            self.logger.info(
                "历史72h自动清理完成: history_removed=%s, output_dirs_removed=%s",
                removed_records,
                removed_output_dirs,
            )
        return removed_records, removed_output_dirs

    def _worker(self) -> None:
        while True:
            try:
                self.cleanup_once()
            except Exception as exc:
                self.logger.warning("历史72h自动清理任务异常: %s", exc)
            time.sleep(self.scan_interval_seconds)

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
            try:
                self.cleanup_once()
            except Exception as exc:
                self.logger.warning("历史72h自动清理首轮执行失败: %s", exc)
            thread = Thread(
                target=self._worker,
                name="history-retention-cleanup",
                daemon=True,
            )
            thread.start()
            self._thread = thread
