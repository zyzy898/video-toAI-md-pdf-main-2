"""Chunked-upload session and upload-video auto-cleanup services.

UploadSessionService tracks resumable chunked uploads, keeping sensitive
fields (model API key) in memory only -- never written to the on-disk
session JSON. UploadVideoAutoCleanupService deletes stale uploaded videos
after a TTL via a daemon thread. Locks for session access are supplied by
the caller.
"""

import json
import logging
import os
import time
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Dict, List

from werkzeug.utils import secure_filename

from path_utils import _assert_within
from utils import _safe_int


class UploadSessionService:
    def __init__(
        self,
        session_root: Path,
        memory_buffers: Dict[str, Dict[int, bytes]],
        memory_reserved_bytes: Dict[str, int],
        max_memory_total_bytes: int,
        logger_obj: logging.Logger,
    ):
        self.session_root = session_root
        self.memory_buffers = memory_buffers
        self.memory_reserved_bytes = memory_reserved_bytes
        self.max_memory_total_bytes = max_memory_total_bytes
        self.logger = logger_obj
        self._reserved_total_bytes = 0
        # 敏感字段（模型 API Key）仅驻留内存，不随会话 JSON 落盘，避免明文残留磁盘。
        self._session_secrets: Dict[str, Dict[str, str]] = {}

    # 不落盘的敏感字段名
    _SECRET_FIELDS = ("risk_api_key",)

    @property
    def reserved_total_bytes(self) -> int:
        return self._reserved_total_bytes

    def normalize_upload_id(self, raw_upload_id: Any) -> str:
        upload_id = secure_filename(str(raw_upload_id or "")).strip()
        if not upload_id:
            return ""
        if len(upload_id) > 120:
            raise ValueError("upload_id 无效")
        return upload_id

    def session_json_path(self, upload_id: str) -> Path:
        session_path = (self.session_root / f"{upload_id}.json").resolve(strict=False)
        _assert_within(session_path, self.session_root, "upload_id")
        return session_path

    def session_temp_path(self, upload_id: str) -> Path:
        temp_path = (self.session_root / f"{upload_id}.part").resolve(strict=False)
        _assert_within(temp_path, self.session_root, "upload_id")
        return temp_path

    def normalize_received_chunks(self, raw_chunks: Any, total_chunks: int) -> List[int]:
        if total_chunks <= 0 or not isinstance(raw_chunks, list):
            return []
        received: set[int] = set()
        for item in raw_chunks:
            idx = _safe_int(item, -1)
            if 0 <= idx < total_chunks:
                received.add(idx)
        return sorted(received)

    def load(self, upload_id: str) -> Dict[str, Any] | None:
        session_path = self.session_json_path(upload_id)
        if not session_path.exists():
            return None
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                session = json.load(f)
            if not isinstance(session, dict):
                return None
        except (OSError, json.JSONDecodeError):
            return None
        # 从内存还原敏感字段；进程重启后内存丢失，敏感字段为空（调用方据此重新校验）。
        secrets_for_id = self._session_secrets.get(upload_id, {})
        for field in self._SECRET_FIELDS:
            session[field] = secrets_for_id.get(field, "")
        return session

    def save(self, upload_id: str, session: Dict[str, Any]) -> None:
        session_path = self.session_json_path(upload_id)
        # 抽出敏感字段存内存，落盘副本中清空它们。
        stored_secrets = self._session_secrets.setdefault(upload_id, {})
        persistable = dict(session)
        for field in self._SECRET_FIELDS:
            if field in session:
                stored_secrets[field] = str(session.get(field, "") or "")
            persistable[field] = ""
        tmp_path = session_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(persistable, f, ensure_ascii=False, indent=2)
        tmp_path.replace(session_path)

    def delete(self, upload_id: str) -> None:
        self.release_memory(upload_id)
        self._session_secrets.pop(upload_id, None)
        for path in (self.session_json_path(upload_id), self.session_temp_path(upload_id)):
            if not path.exists():
                continue
            try:
                path.unlink()
            except OSError:
                self.logger.warning("删除上传会话文件失败: %s", path)

    def reserve_memory(self, upload_id: str, total_size: int) -> bool:
        size = _safe_int(total_size, 0, 0)
        if size <= 0:
            return False
        if upload_id in self.memory_reserved_bytes:
            self.memory_buffers.setdefault(upload_id, {})
            return True
        if self._reserved_total_bytes + size > self.max_memory_total_bytes:
            return False
        self.memory_reserved_bytes[upload_id] = size
        self._reserved_total_bytes += size
        self.memory_buffers.setdefault(upload_id, {})
        return True

    def release_memory(self, upload_id: str) -> None:
        reserved = self.memory_reserved_bytes.pop(upload_id, 0)
        if reserved > 0:
            self._reserved_total_bytes = max(0, self._reserved_total_bytes - reserved)
        self.memory_buffers.pop(upload_id, None)

    def get_chunk_storage_mode(self, session: Dict[str, Any]) -> str:
        mode = str(session.get("storage_mode", "disk")).strip().lower()
        return "memory" if mode == "memory" else "disk"


class UploadVideoAutoCleanupService:
    def __init__(
        self,
        upload_root: Path,
        allowed_extensions: set[str],
        ttl_seconds: int,
        scan_interval_seconds: int,
        logger_obj: logging.Logger,
    ):
        self.upload_root = upload_root
        self.allowed_extensions = {str(ext).strip().lower() for ext in allowed_extensions if str(ext).strip()}
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.scan_interval_seconds = max(60, int(scan_interval_seconds))
        self.logger = logger_obj
        self._start_lock = Lock()
        self._started = False
        self._thread: Thread | None = None

    def _is_video_file(self, path: Path) -> bool:
        if path.is_symlink() or (not path.is_file()):
            return False
        suffix = path.suffix.lower().lstrip(".")
        return bool(suffix and suffix in self.allowed_extensions)

    def _resolve_safe_upload_video_path(self, path: Path) -> Path | None:
        try:
            resolved = path.resolve(strict=False)
            _assert_within(resolved, self.upload_root, "upload_video_path")
            if resolved.is_symlink() or (not resolved.is_file()):
                return None
            suffix = resolved.suffix.lower().lstrip(".")
            if not suffix or suffix not in self.allowed_extensions:
                return None
            return resolved
        except (ValueError, OSError):
            return None

    def _iter_upload_video_files(self):
        if not self.upload_root.exists():
            return
        seen: set[Path] = set()
        for path in self.upload_root.rglob("*"):
            safe_path = self._resolve_safe_upload_video_path(path)
            if safe_path is None or safe_path in seen:
                continue
            seen.add(safe_path)
            yield safe_path

    def mark_loaded_now(self, video_path: Path) -> None:
        try:
            resolved = video_path.resolve(strict=False)
            _assert_within(resolved, self.upload_root, "upload_video_path")
            if not self._is_video_file(resolved):
                return
            os.utime(resolved, None)
        except (ValueError, OSError):
            # Silent by design: auto-cleanup timestamp refresh should not affect upload flow.
            return

    def cleanup_once(self) -> int:
        expire_before_ts = time.time() - float(self.ttl_seconds)
        deleted_count = 0
        for video_file in self._iter_upload_video_files():
            # Secondary boundary validation right before deletion.
            safe_delete_target = self._resolve_safe_upload_video_path(video_file)
            if safe_delete_target is None:
                continue
            try:
                loaded_ts = float(safe_delete_target.stat().st_mtime)
            except (FileNotFoundError, OSError):
                continue
            if loaded_ts > expire_before_ts:
                continue
            try:
                safe_delete_target.unlink()
                deleted_count += 1
            except (FileNotFoundError, OSError):
                continue
        if deleted_count > 0:
            self.logger.info("上传目录 24h 自动清理完成，删除视频文件: %s", deleted_count)
        return deleted_count

    def _worker(self) -> None:
        while True:
            try:
                self.cleanup_once()
            except Exception as exc:
                self.logger.warning("上传目录自动清理任务异常: %s", exc)
            time.sleep(self.scan_interval_seconds)

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
            try:
                self.cleanup_once()
            except Exception as exc:
                self.logger.warning("启动上传目录自动清理时执行首轮清理失败: %s", exc)
            thread = Thread(
                target=self._worker,
                name="upload-video-auto-cleanup",
                daemon=True,
            )
            thread.start()
            self._thread = thread
