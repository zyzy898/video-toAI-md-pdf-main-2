"""Chunked-upload session and upload-video auto-cleanup services.

UploadSessionService tracks resumable chunked uploads, keeping sensitive
fields (model API key) in memory only -- never written to the on-disk
session JSON. UploadVideoAutoCleanupService deletes stale uploaded videos
after a TTL via a daemon thread. Locks for session access are supplied by
the caller.
"""

import hashlib
import hmac
import json
import logging
import os
import stat
import time
from contextlib import nullcontext
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable, ContextManager, Dict, Iterable, List

from werkzeug.utils import secure_filename

from path_utils import _assert_within
from services.path_builders import sanitize_upload_filename
from utils import _safe_int


def _normalize_sha256(value: Any) -> str:
    fingerprint = str(value or "").strip().lower()
    if len(fingerprint) != 64:
        return ""
    if any(char not in "0123456789abcdef" for char in fingerprint):
        return ""
    return fingerprint


def _stat_identity(stat_result: os.stat_result) -> Dict[str, int]:
    return {
        "device": int(stat_result.st_dev),
        "inode": int(stat_result.st_ino),
        "ctime_ns": int(stat_result.st_ctime_ns),
    }


def _identity_matches(expected: Any, actual: Dict[str, int]) -> bool:
    if not isinstance(expected, dict):
        return False
    return all(
        _safe_int(expected.get(key), -1) == value for key, value in actual.items()
    )


def _compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


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
        raw_value = str(raw_upload_id or "").strip()
        if not raw_value:
            return ""
        if len(raw_value) > 120:
            raise ValueError("upload_id 无效")
        upload_id = secure_filename(raw_value).strip()
        if not upload_id or upload_id != raw_value:
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

    def reserve_unique_destination(
        self,
        filename: str,
        *,
        upload_root: Path,
        reservation_token: str | None = None,
    ) -> Path:
        safe_name = sanitize_upload_filename(filename, fallback_name="upload.mp4")
        base_path = (upload_root / safe_name).resolve(strict=False)
        _assert_within(base_path, upload_root, "upload_destination")
        upload_root.mkdir(parents=True, exist_ok=True)
        stem = base_path.stem
        suffix = base_path.suffix
        raw_token = str(reservation_token or "").strip()
        if raw_token:
            safe_token = self.normalize_upload_id(raw_token)
            stem_budget = max(1, 220 - len(safe_token) - len(suffix) - 1)
            safe_stem = stem[:stem_budget].rstrip(" ._") or "upload"
            stem = f"{safe_stem}_{safe_token}"
            base_path = (upload_root / f"{stem}{suffix}").resolve(strict=False)
            _assert_within(base_path, upload_root, "upload_destination")
        counter = 0
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY

        while True:
            candidate = base_path if counter == 0 else upload_root / f"{stem}_{counter}{suffix}"
            try:
                descriptor = os.open(candidate, flags, 0o600)
            except FileExistsError:
                counter += 1
                continue
            os.close(descriptor)
            return candidate

    def completed_result_is_owned(
        self,
        session: Dict[str, Any],
        *,
        upload_root: Path,
    ) -> bool:
        if str(session.get("status", "")).strip().lower() != "completed":
            return False
        result = session.get("result")
        expected_identity = session.get("result_destination_identity")
        expected_fingerprint = _normalize_sha256(session.get("result_file_sha256"))
        expected_size = _safe_int(session.get("total_size"), -1)
        if (
            not isinstance(result, dict)
            or not isinstance(expected_identity, dict)
            or not expected_fingerprint
            or expected_size < 0
        ):
            return False

        try:
            result_path = self.resolve_destination_path(result, upload_root=upload_root)
            before_stat = result_path.stat()
        except (FileNotFoundError, ValueError):
            return False
        before_identity = _stat_identity(before_stat)
        if (
            not stat.S_ISREG(before_stat.st_mode)
            or before_stat.st_size != expected_size
            or not _identity_matches(expected_identity, before_identity)
        ):
            return False

        try:
            actual_fingerprint = _compute_sha256(result_path)
            after_stat = result_path.stat()
        except FileNotFoundError:
            return False
        after_identity = _stat_identity(after_stat)
        if (
            after_stat.st_size != expected_size
            or after_identity != before_identity
            or not _identity_matches(expected_identity, after_identity)
        ):
            return False
        return hmac.compare_digest(actual_fingerprint, expected_fingerprint)

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

    def delete(self, upload_id: str) -> bool:
        deleted = True
        for path in (self.session_json_path(upload_id), self.session_temp_path(upload_id)):
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                deleted = False
                self.logger.warning("删除上传会话文件失败: %s", path)
        if deleted:
            self.release_memory(upload_id)
            self._session_secrets.pop(upload_id, None)
        return deleted

    def cleanup_stale_sessions(
        self,
        *,
        upload_root: Path,
        ttl_seconds: int,
        now: float | None = None,
    ) -> int:
        if not self.session_root.exists():
            return 0

        safe_upload_root = upload_root.expanduser().resolve(strict=False)
        expire_before = float(time.time() if now is None else now) - max(
            1, int(ttl_seconds)
        )
        deleted_count = 0

        def is_stale(path: Path) -> bool:
            try:
                return float(path.stat().st_mtime) <= expire_before
            except (FileNotFoundError, OSError):
                return False

        def completed_result_exists(session: Dict[str, Any]) -> bool:
            if str(session.get("status", "")).strip().lower() != "completed":
                return True
            try:
                return self.completed_result_is_owned(
                    session,
                    upload_root=safe_upload_root,
                )
            except ValueError:
                return False
            except OSError as exc:
                self.logger.warning("验证上传完成回执时发生临时文件错误: %s", exc)
                return True

        for session_path in list(self.session_root.glob("*.json")):
            try:
                with open(session_path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                session = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError):
                session = None

            should_delete = is_stale(session_path)
            if session is not None and not completed_result_exists(session):
                should_delete = True
            if not should_delete:
                continue

            upload_id = session_path.stem
            before = sum(
                int(path.exists())
                for path in (session_path, self.session_temp_path(upload_id))
            )
            self.delete(upload_id)
            after = sum(
                int(path.exists())
                for path in (session_path, self.session_temp_path(upload_id))
            )
            deleted_count += max(0, before - after)

        for pattern in ("*.part", "*.tmp"):
            for artifact in list(self.session_root.glob(pattern)):
                if pattern == "*.part" and artifact.with_suffix(".json").exists():
                    continue
                if not is_stale(artifact):
                    continue
                try:
                    artifact.unlink()
                    deleted_count += 1
                except FileNotFoundError:
                    continue
                except OSError:
                    self.logger.warning("删除过期上传会话文件失败: %s", artifact)

        if deleted_count > 0:
            self.logger.info("上传会话清理完成，删除文件: %s", deleted_count)
        return deleted_count

    def resolve_destination_path(
        self,
        result_payload: Dict[str, Any],
        *,
        upload_root: Path,
    ) -> Path:
        raw_path = str(result_payload.get("filepath", "")).strip()
        if not raw_path:
            raise ValueError("上传完成路径无效")
        raw_candidate = Path(raw_path).expanduser()
        if raw_candidate.is_symlink():
            raise ValueError("上传完成路径无效")
        safe_upload_root = upload_root.expanduser().resolve(strict=False)
        resolved = raw_candidate.resolve(strict=False)
        _assert_within(resolved, safe_upload_root, "upload_destination")
        if resolved.parent != safe_upload_root:
            raise ValueError("上传完成路径无效")
        expected_name = str(result_payload.get("filename", "")).strip()
        if expected_name and expected_name != resolved.name:
            raise ValueError("上传完成路径无效")
        return resolved

    def pending_destination_paths(self, *, upload_root: Path) -> set[Path]:
        protected: set[Path] = set()
        if not self.session_root.exists():
            return protected
        for session_path in self.session_root.glob("*.json"):
            try:
                with open(session_path, "r", encoding="utf-8") as handle:
                    session = json.load(handle)
                if not isinstance(session, dict):
                    continue
                if str(session.get("status", "")).strip().lower() != "finalizing":
                    continue
                if bool(session.get("pending_destination_deleted")):
                    continue
                pending_result = session.get("pending_result")
                if not isinstance(pending_result, dict):
                    continue
                protected.add(
                    self.resolve_destination_path(
                        pending_result,
                        upload_root=upload_root,
                    )
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return protected

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
        session_cleanup: Callable[[], int] | None = None,
        protected_paths_provider: Callable[[], Iterable[Path]] | None = None,
        operation_lock: ContextManager[Any] | None = None,
    ):
        self.upload_root = upload_root
        self.allowed_extensions = {str(ext).strip().lower() for ext in allowed_extensions if str(ext).strip()}
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.scan_interval_seconds = max(60, int(scan_interval_seconds))
        self.logger = logger_obj
        self.session_cleanup = session_cleanup
        self.protected_paths_provider = protected_paths_provider
        self.operation_lock = operation_lock
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
        with self.operation_lock or nullcontext():
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
        with self.operation_lock or nullcontext():
            expire_before_ts = time.time() - float(self.ttl_seconds)

            def cleanup_sessions() -> int:
                if self.session_cleanup is None:
                    return 0
                try:
                    return max(0, int(self.session_cleanup()))
                except Exception as exc:
                    self.logger.warning("上传会话自动清理异常: %s", exc)
                    return 0

            session_deleted_count = cleanup_sessions()

            protected_paths: set[Path] = set()
            if self.protected_paths_provider is not None:
                try:
                    protected_paths = {
                        path.expanduser().resolve(strict=False)
                        for path in self.protected_paths_provider()
                    }
                except Exception as exc:
                    self.logger.warning("获取上传会话保护路径失败: %s", exc)
                    return 0

            deleted_count = 0
            for video_file in self._iter_upload_video_files():
                safe_delete_target = self._resolve_safe_upload_video_path(video_file)
                if safe_delete_target is None or safe_delete_target in protected_paths:
                    continue
                try:
                    initial_stat = safe_delete_target.stat()
                except (FileNotFoundError, OSError):
                    continue
                if float(initial_stat.st_mtime) > expire_before_ts:
                    continue
                try:
                    current_stat = safe_delete_target.stat()
                    identity_changed = (
                        current_stat.st_dev != initial_stat.st_dev
                        or current_stat.st_ino != initial_stat.st_ino
                        or current_stat.st_mtime_ns != initial_stat.st_mtime_ns
                        or current_stat.st_size != initial_stat.st_size
                    )
                    if identity_changed or float(current_stat.st_mtime) > expire_before_ts:
                        continue
                    safe_delete_target.unlink()
                    deleted_count += 1
                except (FileNotFoundError, OSError):
                    continue
            if deleted_count > 0:
                session_deleted_count += cleanup_sessions()
            if deleted_count > 0:
                self.logger.info("上传目录 24h 自动清理完成，删除视频文件: %s", deleted_count)
            if session_deleted_count > 0:
                self.logger.info("上传目录 24h 自动清理完成，删除会话文件: %s", session_deleted_count)
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
