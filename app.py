import asyncio
import base64
import hashlib
import json
import logging
import os
import random
import re
import shutil
import subprocess
import traceback
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, RLock
from typing import Any, Callable, Dict, List, Tuple
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from video_analyzer_agent import VideoAnalyzerAgent

app = Flask(__name__)
app.secret_key = "video-analyzer-secret-key"
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = (PROJECT_ROOT / "uploads").resolve()
OUTPUT_ROOT = (PROJECT_ROOT / "outputs").resolve()
HISTORY_PATH = (PROJECT_ROOT / "history.json").resolve()
UPLOAD_SESSION_ROOT = (UPLOAD_ROOT / ".upload_sessions").resolve()

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_ROOT)
app.config["OUTPUT_FOLDER"] = str(OUTPUT_ROOT)

ALLOWED_EXTENSIONS = {
    "mp4",
    "avi",
    "mov",
    "mkv",
    "wmv",
    "flv",
    "webm",
    "m4v",
    "mpg",
    "mpeg",
    "3gp",
    "ts",
    "m2ts",
}
ALLOWED_WHISPER_MODELS = {"tiny", "base", "small", "medium", "large"}
MAX_HISTORY = 50
MAX_VISION_CALLS = 10
FPS_MIN = 0.1
FPS_MAX = 10.0
DEFAULT_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
MAX_UPLOAD_CHUNK_SIZE = 32 * 1024 * 1024
UPLOAD_IN_MEMORY_MAX_FILE_SIZE = 64 * 1024 * 1024
UPLOAD_IN_MEMORY_MAX_TOTAL_BYTES = 256 * 1024 * 1024
DEFAULT_MODEL_NAME = "doubao-seed-2-0-pro-260215"
DEFAULT_MODEL_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
WEB_SEARCH_ACTIVATION_URL = "https://console.volcengine.com/common-buy/CC_content_plugin"
RISK_MAX_FRAMES = 6
RISK_MIN_FRAMES = 3
RISK_DYNAMIC_MAX_FRAMES = 15
RISK_FRAME_GROWTH_START_SECONDS = 20
RISK_FRAME_GROWTH_EVERY_SECONDS = 45
RISK_BLOCK_THRESHOLD = 0.8
RISK_RESTRICT_THRESHOLD = 0.55
RISK_BLOCK_ON_RESTRICT = True
RISK_DIMENSION_HARD_BLOCK_SCORE = 0.72
RISK_CRITICAL_SCORE = 0.9
CONTENT_POLICY_BLOCK_MESSAGE = (
    "上传已被风控强拦截：检测到高风险色情/裸露/血腥/暴力内容，"
    "系统已直接拒绝该视频上传。请删除敏感画面后重试"
)
TEXT_RISK_BLOCK_THRESHOLD = 0.78
TEXT_RISK_RESTRICT_THRESHOLD = 0.5
ENV_FILE_PATH = (PROJECT_ROOT / ".env").resolve()
RISK_FALLBACK_ENV_BLOCK_MARKER = "# ===== 风控视觉兜底（仅系统管理员） ====="
RISK_FALLBACK_ENV_BLOCK_MARKER_LEGACY = "# ===== RISK VISUAL FALLBACK (SYSTEM ADMIN ONLY) ====="
RISK_FALLBACK_ENV_KEYS = (
    "RISK_FALLBACK_API_KEY",
    "RISK_FALLBACK_MODEL_NAME",
    "RISK_FALLBACK_MODEL_BASE_URL",
)
HISTORY_OWNER_HEADER = "X-Client-ID"
HISTORY_OWNER_COOKIE = "video_insights_client_id"
HISTORY_OWNER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2
HISTORY_OWNER_MAX_LEN = 120
HISTORY_OWNER_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
QUARANTINE_ROOT = (UPLOAD_ROOT / ".quarantine").resolve()
UPLOAD_STAGING_ROOT = (UPLOAD_ROOT / ".staging").resolve()
RISK_KEYWORD_LEXICON_PATH = (PROJECT_ROOT / "risk_keyword_lexicon.json").resolve()
RISK_BLOCKLIST_PATH = (UPLOAD_ROOT / ".risk_blocklist.json").resolve()
RISK_RESULT_CACHE_PATH = (UPLOAD_ROOT / ".risk_result_cache.json").resolve()
RISK_RESULT_CACHE_TTL_SECONDS = 60 * 60 * 24
RISK_RESULT_CACHE_MAX_ENTRIES = 500

UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_SESSION_ROOT.mkdir(parents=True, exist_ok=True)
QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_STAGING_ROOT.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
history_lock = RLock()
upload_session_lock = RLock()
batch_progress_lock = Lock()
batch_progress: Dict[str, Any] = {
    "total": 0,
    "current": 0,
    "status": "idle",
    "current_file": "",
    "stage": "idle",
    "message": "",
}
single_progress_lock = Lock()
single_progress: Dict[str, Any] = {
    "status": "idle",
    "current_file": "",
    "stage": "idle",
    "message": "",
}
upload_memory_buffers: Dict[str, Dict[int, bytes]] = {}
upload_memory_reserved_bytes: Dict[str, int] = {}
upload_memory_reserved_total_bytes = 0
risk_keyword_lexicon_lock = RLock()
risk_keyword_lexicon_cache_mtime_ns: int | None = None
risk_keyword_lexicon_cache_data: Dict[str, Dict[str, Any]] | None = None
risk_blocklist_lock = RLock()
risk_result_cache_lock = RLock()


class RiskFallbackEnvService:
    def __init__(
        self,
        env_path: Path,
        block_marker: str,
        legacy_marker: str,
        env_keys: Tuple[str, str, str],
        logger_obj: logging.Logger,
    ):
        self.env_path = env_path
        self.block_marker = block_marker
        self.legacy_marker = legacy_marker
        self.env_keys = env_keys
        self.logger = logger_obj

    def ensure_env_file(self) -> None:
        info_lines = [
            self.block_marker,
            "# 系统自动创建，请勿向普通用户暴露。",
            "# 该兜底模型必须是视觉模型（支持图片输入）。",
            "# 仅在主视觉风控模型不可用时启用。",
        ]
        expected_lines = [*info_lines, *(f"{key}=" for key in self.env_keys)]
        try:
            if not self.env_path.exists():
                self.env_path.write_text("\n".join(expected_lines) + "\n", encoding="utf-8")
                return

            raw_text = self.env_path.read_text(encoding="utf-8")
            missing_keys = [
                key
                for key in self.env_keys
                if re.search(rf"^\s*{re.escape(key)}\s*=", raw_text, re.MULTILINE) is None
            ]
            missing_marker = (
                self.block_marker not in raw_text
                and self.legacy_marker not in raw_text
            )
            if not missing_keys and not missing_marker:
                return

            append_lines: List[str] = []
            if missing_marker:
                append_lines.extend(info_lines)
            append_lines.extend(f"{key}=" for key in missing_keys)
            if not append_lines:
                return

            with open(self.env_path, "a", encoding="utf-8") as f:
                if raw_text and not raw_text.endswith(("\n", "\r")):
                    f.write("\n")
                f.write("\n".join(append_lines) + "\n")
        except (OSError, UnicodeDecodeError) as exc:
            self.logger.warning("无法自动维护 .env 风控兜底模板: %s", exc)

    def read_model_options(self) -> Tuple[str, str, str]:
        api_key = str(os.getenv("RISK_FALLBACK_API_KEY", "")).strip()
        model_name = str(os.getenv("RISK_FALLBACK_MODEL_NAME", "")).strip()
        model_base_url = str(os.getenv("RISK_FALLBACK_MODEL_BASE_URL", "")).strip()
        return api_key, model_name, model_base_url


class ProgressStateService:
    def __init__(
        self,
        batch_state: Dict[str, Any],
        batch_lock_obj: Lock,
        single_state: Dict[str, Any],
        single_lock_obj: Lock,
    ):
        self.batch_state = batch_state
        self.batch_lock = batch_lock_obj
        self.single_state = single_state
        self.single_lock = single_lock_obj

    def update_batch(self, **kwargs: Any) -> None:
        with self.batch_lock:
            self.batch_state.update(kwargs)

    def update_single(self, **kwargs: Any) -> None:
        with self.single_lock:
            self.single_state.update(kwargs)

    def get_batch_snapshot(self) -> Dict[str, Any]:
        with self.batch_lock:
            return dict(self.batch_state)

    def get_single_snapshot(self) -> Dict[str, Any]:
        with self.single_lock:
            return dict(self.single_state)


risk_fallback_env_service = RiskFallbackEnvService(
    env_path=ENV_FILE_PATH,
    block_marker=RISK_FALLBACK_ENV_BLOCK_MARKER,
    legacy_marker=RISK_FALLBACK_ENV_BLOCK_MARKER_LEGACY,
    env_keys=RISK_FALLBACK_ENV_KEYS,
    logger_obj=logger,
)
progress_state_service = ProgressStateService(
    batch_state=batch_progress,
    batch_lock_obj=batch_progress_lock,
    single_state=single_progress,
    single_lock_obj=single_progress_lock,
)


def _ensure_risk_fallback_env_file() -> None:
    risk_fallback_env_service.ensure_env_file()


def _read_risk_fallback_env_model_options() -> Tuple[str, str, str]:
    return risk_fallback_env_service.read_model_options()


_ensure_risk_fallback_env_file()


class ContentPolicyBlockedError(RuntimeError):
    def __init__(self, message: str, risk: Dict[str, Any]):
        super().__init__(message)
        self.risk = risk


def _update_batch_progress(**kwargs: Any) -> None:
    progress_state_service.update_batch(**kwargs)


def _update_single_progress(**kwargs: Any) -> None:
    progress_state_service.update_single(**kwargs)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _safe_int(
    value: Any, default: int, min_value: int | None = None, max_value: int | None = None
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number


def _safe_float(
    value: Any,
    default: float,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number


class RiskBlocklistService:
    def __init__(self, blocklist_path: Path, lock_obj: RLock, logger_obj: logging.Logger):
        self.blocklist_path = blocklist_path
        self.lock = lock_obj
        self.logger = logger_obj

    def normalize_sha256_fingerprint(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^0-9a-f]", "", text)
        return text if len(text) == 64 else ""

    def compute_file_sha256(self, file_path: Path, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(max(4096, int(chunk_size)))
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def normalize_entry(self, raw_entry: Any) -> Dict[str, Any] | None:
        if not isinstance(raw_entry, dict):
            return None
        sha256 = self.normalize_sha256_fingerprint(raw_entry.get("sha256", ""))
        if not sha256:
            return None

        reason_code = str(raw_entry.get("reason_code", "CONTENT_POLICY_VIOLATION")).strip().upper()
        reason = str(raw_entry.get("reason", "")).strip()
        if len(reason) > 320:
            reason = reason[:320]

        return {
            "sha256": sha256,
            "decision": str(raw_entry.get("decision", "block")).strip().lower() or "block",
            "risk_level": str(raw_entry.get("risk_level", "high")).strip().lower() or "high",
            "reason_code": reason_code or "CONTENT_POLICY_VIOLATION",
            "reason": reason,
            "first_blocked_at": str(raw_entry.get("first_blocked_at", "")).strip(),
            "last_blocked_at": str(raw_entry.get("last_blocked_at", "")).strip(),
            "last_blocked_source": str(raw_entry.get("last_blocked_source", "")).strip(),
            "block_count": _safe_int(raw_entry.get("block_count", 0), 0, 0),
            "last_match_at": str(raw_entry.get("last_match_at", "")).strip(),
            "last_match_source": str(raw_entry.get("last_match_source", "")).strip(),
            "match_count": _safe_int(raw_entry.get("match_count", 0), 0, 0),
        }

    def load_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if not self.blocklist_path.exists():
            return {}
        try:
            with open(self.blocklist_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("读取风控黑名单失败，已忽略该文件: %s", exc)
            return {}

        raw_entries: List[Any] = []
        if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
            raw_entries = payload.get("entries", [])
        elif isinstance(payload, list):
            raw_entries = payload
        else:
            return {}

        entries: Dict[str, Dict[str, Any]] = {}
        for item in raw_entries:
            normalized = self.normalize_entry(item)
            if normalized is None:
                continue
            entries[normalized["sha256"]] = normalized
        return entries

    def write_unlocked(self, entries: Dict[str, Dict[str, Any]]) -> None:
        ordered_entries = sorted(
            entries.values(),
            key=lambda item: str(item.get("last_blocked_at", "")).strip(),
            reverse=True,
        )
        payload = {
            "version": 1,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entries": ordered_entries,
        }
        tmp_path = self.blocklist_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.blocklist_path)

    def build_match_risk(self, fingerprint: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        reason_code = str(entry.get("reason_code", "BLACKLIST_EXACT_HASH_MATCH")).strip().upper()
        reason = (
            "命中违规视频黑名单指纹（SHA-256 完全一致），已直接拒绝。"
            f" 指纹：{fingerprint}"
        )
        return {
            "decision": "block",
            "risk_level": "high",
            "reason_code": "BLACKLIST_EXACT_HASH_MATCH",
            "reason": reason,
            "confidence": 1.0,
            "scores": {"nudity": 1.0, "violence": 1.0, "gore": 1.0},
            "dimensions": {},
            "frame_count": 0,
            "hash_sha256": fingerprint,
            "blacklist_reason_code": reason_code,
            "blacklist_block_count": _safe_int(entry.get("block_count", 0), 0, 0),
            "blacklist_match_count": _safe_int(entry.get("match_count", 0), 0, 0),
        }

    def match_fingerprint(self, fingerprint: str, source: str) -> Dict[str, Any] | None:
        normalized_fingerprint = self.normalize_sha256_fingerprint(fingerprint)
        if not normalized_fingerprint:
            return None

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            entries = self.load_unlocked()
            existing = entries.get(normalized_fingerprint)
            if existing is None:
                return None

            existing["last_match_at"] = now_text
            existing["last_match_source"] = str(source or "").strip()
            existing["match_count"] = _safe_int(existing.get("match_count", 0), 0, 0) + 1
            entries[normalized_fingerprint] = existing
            try:
                self.write_unlocked(entries)
            except OSError as exc:
                self.logger.warning("更新风控黑名单命中计数失败: %s", exc)

        return self.build_match_risk(normalized_fingerprint, existing)

    def match_video_fingerprint(self, video_path: Path, source: str) -> Dict[str, Any] | None:
        try:
            fingerprint = self.compute_file_sha256(video_path)
        except OSError as exc:
            self.logger.warning("计算视频指纹失败，跳过黑名单比对: %s", exc)
            return None
        return self.match_fingerprint(fingerprint, source)

    def register_blocked_fingerprint(
        self, fingerprint: str, risk: Dict[str, Any], source: str
    ) -> str:
        normalized_fingerprint = self.normalize_sha256_fingerprint(fingerprint)
        if not normalized_fingerprint:
            return ""

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reason_code = str(risk.get("reason_code", "CONTENT_POLICY_VIOLATION")).strip().upper()
        reason = str(risk.get("reason", "")).strip()
        if len(reason) > 320:
            reason = reason[:320]
        decision = str(risk.get("decision", "block")).strip().lower() or "block"
        risk_level = str(risk.get("risk_level", "high")).strip().lower() or "high"

        with self.lock:
            entries = self.load_unlocked()
            existing = entries.get(normalized_fingerprint, {})
            entry = {
                "sha256": normalized_fingerprint,
                "decision": decision,
                "risk_level": risk_level,
                "reason_code": reason_code or "CONTENT_POLICY_VIOLATION",
                "reason": reason,
                "first_blocked_at": str(existing.get("first_blocked_at", "")).strip() or now_text,
                "last_blocked_at": now_text,
                "last_blocked_source": str(source or "").strip(),
                "block_count": _safe_int(existing.get("block_count", 0), 0, 0) + 1,
                "last_match_at": str(existing.get("last_match_at", "")).strip(),
                "last_match_source": str(existing.get("last_match_source", "")).strip(),
                "match_count": _safe_int(existing.get("match_count", 0), 0, 0),
            }
            entries[normalized_fingerprint] = entry
            try:
                self.write_unlocked(entries)
            except OSError as exc:
                self.logger.warning("写入风控黑名单失败: %s", exc)

        return normalized_fingerprint

    def register_blocked_video_fingerprint(
        self, video_path: Path, risk: Dict[str, Any], source: str
    ) -> str:
        try:
            fingerprint = self.compute_file_sha256(video_path)
        except OSError as exc:
            self.logger.warning("计算违规视频指纹失败，无法写入黑名单: %s", exc)
            return ""
        return self.register_blocked_fingerprint(fingerprint, risk, source)


risk_blocklist_service = RiskBlocklistService(
    blocklist_path=RISK_BLOCKLIST_PATH,
    lock_obj=risk_blocklist_lock,
    logger_obj=logger,
)


def _normalize_sha256_fingerprint(value: Any) -> str:
    return risk_blocklist_service.normalize_sha256_fingerprint(value)


def _compute_file_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    return risk_blocklist_service.compute_file_sha256(file_path, chunk_size=chunk_size)


def _normalize_risk_blocklist_entry(raw_entry: Any) -> Dict[str, Any] | None:
    return risk_blocklist_service.normalize_entry(raw_entry)


def _load_risk_blocklist_unlocked() -> Dict[str, Dict[str, Any]]:
    return risk_blocklist_service.load_unlocked()


def _write_risk_blocklist_unlocked(entries: Dict[str, Dict[str, Any]]) -> None:
    risk_blocklist_service.write_unlocked(entries)


def _build_blacklist_match_risk(fingerprint: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    return risk_blocklist_service.build_match_risk(fingerprint, entry)


def _match_blacklisted_video_fingerprint_by_hash(
    fingerprint: str, source: str
) -> Dict[str, Any] | None:
    return risk_blocklist_service.match_fingerprint(fingerprint, source)


def _match_blacklisted_video_fingerprint(video_path: Path, source: str) -> Dict[str, Any] | None:
    return risk_blocklist_service.match_video_fingerprint(video_path, source)


def _register_blocked_video_fingerprint_by_hash(
    fingerprint: str, risk: Dict[str, Any], source: str
) -> str:
    return risk_blocklist_service.register_blocked_fingerprint(fingerprint, risk, source)


def _register_blocked_video_fingerprint(
    video_path: Path, risk: Dict[str, Any], source: str
) -> str:
    return risk_blocklist_service.register_blocked_video_fingerprint(video_path, risk, source)


class RiskResultCacheService:
    def __init__(
        self,
        cache_path: Path,
        lock_obj: RLock,
        ttl_seconds: int,
        max_entries: int,
        logger_obj: logging.Logger,
    ):
        self.cache_path = cache_path
        self.lock = lock_obj
        self.ttl_seconds = max(60, int(ttl_seconds or 0))
        self.max_entries = max(50, int(max_entries or 0))
        self.logger = logger_obj
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _normalize_sha256(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^0-9a-f]", "", text)
        return text if len(text) == 64 else ""

    def _normalize_key_hash(self, value: Any) -> str:
        return self._normalize_sha256(value)

    def build_model_key(self, model_name: str, model_base_url: str) -> str:
        normalized_name = str(model_name or "").strip().lower()
        normalized_base_url = str(model_base_url or "").strip().rstrip("/").lower()
        policy_signature = "|".join(
            [
                f"rb:{RISK_BLOCK_THRESHOLD:.4f}",
                f"rr:{RISK_RESTRICT_THRESHOLD:.4f}",
                f"bor:{int(RISK_BLOCK_ON_RESTRICT)}",
                f"dh:{RISK_DIMENSION_HARD_BLOCK_SCORE:.4f}",
                f"cs:{RISK_CRITICAL_SCORE:.4f}",
                f"tb:{TEXT_RISK_BLOCK_THRESHOLD:.4f}",
                f"tr:{TEXT_RISK_RESTRICT_THRESHOLD:.4f}",
            ]
        )
        raw = f"{normalized_name}|{normalized_base_url}|{policy_signature}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def build_model_key_from_agent(self, risk_agent: VideoAnalyzerAgent) -> str:
        model_name = str(getattr(risk_agent, "model", "")).strip()
        model_base_url = str(getattr(risk_agent, "base_url", "")).strip()
        return self.build_model_key(model_name, model_base_url)

    def build_cache_key(self, fingerprint: str, model_key: str) -> str:
        normalized_fingerprint = self._normalize_sha256(fingerprint)
        normalized_model_key = self._normalize_key_hash(model_key)
        if not normalized_fingerprint or not normalized_model_key:
            return ""
        return hashlib.sha256(
            f"{normalized_fingerprint}:{normalized_model_key}".encode("utf-8")
        ).hexdigest()

    def normalize_entry(self, raw_entry: Any, now_ts: float) -> Dict[str, Any] | None:
        if not isinstance(raw_entry, dict):
            return None
        fingerprint = self._normalize_sha256(raw_entry.get("sha256", ""))
        model_key = self._normalize_key_hash(raw_entry.get("model_key", ""))
        if not fingerprint or not model_key:
            return None

        cache_key = self._normalize_key_hash(raw_entry.get("cache_key", ""))
        if not cache_key:
            cache_key = self.build_cache_key(fingerprint, model_key)
        if not cache_key:
            return None

        risk = raw_entry.get("risk", {})
        if not isinstance(risk, dict) or not risk:
            return None

        created_at_ts = _safe_float(raw_entry.get("created_at_ts"), now_ts, 0.0)
        expires_at_ts = _safe_float(
            raw_entry.get("expires_at_ts"), created_at_ts + self.ttl_seconds, 0.0
        )
        if expires_at_ts <= now_ts:
            return None

        return {
            "cache_key": cache_key,
            "sha256": fingerprint,
            "model_key": model_key,
            "risk": dict(risk),
            "created_at": str(raw_entry.get("created_at", "")).strip()
            or datetime.fromtimestamp(created_at_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_ts": created_at_ts,
            "expires_at": str(raw_entry.get("expires_at", "")).strip()
            or datetime.fromtimestamp(expires_at_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at_ts": expires_at_ts,
            "hit_count": _safe_int(raw_entry.get("hit_count", 0), 0, 0),
            "last_hit_at": str(raw_entry.get("last_hit_at", "")).strip(),
        }

    def load_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("读取上传风控缓存失败，已忽略: %s", exc)
            return {}

        raw_entries: List[Any] = []
        if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
            raw_entries = payload.get("entries", [])
        elif isinstance(payload, list):
            raw_entries = payload
        else:
            return {}

        now_ts = datetime.now().timestamp()
        entries: Dict[str, Dict[str, Any]] = {}
        for item in raw_entries:
            normalized = self.normalize_entry(item, now_ts)
            if normalized is None:
                continue
            entries[normalized["cache_key"]] = normalized
        return self._prune_unlocked(entries)

    def _prune_unlocked(self, entries: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        now_ts = datetime.now().timestamp()
        valid_entries = [
            entry
            for entry in entries.values()
            if _safe_float(entry.get("expires_at_ts"), 0.0, 0.0) > now_ts
        ]
        valid_entries.sort(
            key=lambda item: _safe_float(item.get("created_at_ts"), 0.0, 0.0),
            reverse=True,
        )
        limited_entries = valid_entries[: self.max_entries]
        return {str(entry.get("cache_key", "")): entry for entry in limited_entries}

    def write_unlocked(self, entries: Dict[str, Dict[str, Any]]) -> None:
        ordered_entries = sorted(
            entries.values(),
            key=lambda item: _safe_float(item.get("created_at_ts"), 0.0, 0.0),
            reverse=True,
        )
        payload = {
            "version": 1,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
            "entries": ordered_entries,
        }
        tmp_path = self.cache_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.cache_path)

    def _ensure_loaded_unlocked(self) -> Dict[str, Dict[str, Any]]:
        if self._loaded:
            self._entries = self._prune_unlocked(self._entries)
            return self._entries
        self._entries = self.load_unlocked()
        self._loaded = True
        return self._entries

    def get(self, fingerprint: str, model_key: str) -> Dict[str, Any] | None:
        cache_key = self.build_cache_key(fingerprint, model_key)
        if not cache_key:
            return None
        with self.lock:
            entries = self._ensure_loaded_unlocked()
            entry = entries.get(cache_key)
            if entry is None:
                return None
            if _safe_float(entry.get("expires_at_ts"), 0.0, 0.0) <= datetime.now().timestamp():
                entries.pop(cache_key, None)
                self._entries = entries
                try:
                    self.write_unlocked(entries)
                except OSError as exc:
                    self.logger.warning("写入上传风控缓存失败: %s", exc)
                return None
            entry["hit_count"] = _safe_int(entry.get("hit_count", 0), 0, 0) + 1
            entry["last_hit_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entries[cache_key] = entry
            self._entries = entries
            risk = entry.get("risk", {})
            return dict(risk) if isinstance(risk, dict) else None

    def set(self, fingerprint: str, model_key: str, risk: Dict[str, Any]) -> None:
        cache_key = self.build_cache_key(fingerprint, model_key)
        normalized_fingerprint = self._normalize_sha256(fingerprint)
        normalized_model_key = self._normalize_key_hash(model_key)
        if not cache_key or not normalized_fingerprint or not normalized_model_key:
            return
        if not isinstance(risk, dict) or not risk:
            return

        now = datetime.now()
        now_ts = now.timestamp()
        expires_at_ts = now_ts + self.ttl_seconds
        entry = {
            "cache_key": cache_key,
            "sha256": normalized_fingerprint,
            "model_key": normalized_model_key,
            "risk": dict(risk),
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_ts": now_ts,
            "expires_at": datetime.fromtimestamp(expires_at_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at_ts": expires_at_ts,
            "hit_count": 0,
            "last_hit_at": "",
        }

        with self.lock:
            entries = self._ensure_loaded_unlocked()
            entries[cache_key] = entry
            entries = self._prune_unlocked(entries)
            self._entries = entries
            try:
                self.write_unlocked(entries)
            except OSError as exc:
                self.logger.warning("写入上传风控缓存失败: %s", exc)


risk_result_cache_service = RiskResultCacheService(
    cache_path=RISK_RESULT_CACHE_PATH,
    lock_obj=risk_result_cache_lock,
    ttl_seconds=RISK_RESULT_CACHE_TTL_SECONDS,
    max_entries=RISK_RESULT_CACHE_MAX_ENTRIES,
    logger_obj=logger,
)


def _build_upload_risk_model_cache_key(model_name: str, model_base_url: str) -> str:
    return risk_result_cache_service.build_model_key(model_name, model_base_url)


def _build_upload_risk_model_cache_key_from_agent(risk_agent: VideoAnalyzerAgent) -> str:
    return risk_result_cache_service.build_model_key_from_agent(risk_agent)


def _get_cached_upload_risk_result(fingerprint: str, model_key: str) -> Dict[str, Any] | None:
    return risk_result_cache_service.get(fingerprint, model_key)


def _set_cached_upload_risk_result(fingerprint: str, model_key: str, risk: Dict[str, Any]) -> None:
    risk_result_cache_service.set(fingerprint, model_key, risk)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _json_payload() -> Dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _extract_request_id(message: str) -> str:
    match = re.search(
        r"request[_\s-]*id['\"]?\s*[:]\s*['\"]?([A-Za-z0-9._-]+)",
        str(message or ""),
        flags=re.IGNORECASE,
    )
    return str(match.group(1)).strip() if match else ""


def _extract_http_status_code(message: str) -> int | None:
    text = str(message or "")
    patterns = (
        r"(?:error\s*code|status\s*code|http(?:\s*status)?)\s*[:=]?\s*(\d{3})",
        r"['\"]status['\"]\s*[:=]\s*(\d{3})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            status_code = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if 100 <= status_code <= 599:
            return status_code
    return None


def _normalize_provider_error(error: Any, default_status: int = 500) -> Tuple[str, int, bool]:
    raw_message = str(error or "").strip() or "模型服务调用失败"
    lower = raw_message.lower()
    request_id = _extract_request_id(raw_message)
    request_id_text = f"（请求 ID：{request_id}）" if request_id else ""

    is_web_search_not_open = (
        "toolnotopen" in lower or "web search" in lower or "联网搜索" in raw_message
    )
    if is_web_search_not_open:
        return (
            f"联网搜索功能未开通。请先开通后重试：{WEB_SEARCH_ACTIVATION_URL}{request_id_text}",
            400,
            True,
        )

    is_auth_error = (
        "authentication fails" in lower
        or "authentication_error" in lower
        or "invalid_api_key" in lower
        or "incorrect api key provided" in lower
        or "api key format is incorrect" in lower
        or ("api key" in lower and ("invalid" in lower or "is invalid" in lower or "无效" in raw_message))
    )
    if is_auth_error:
        return (
            f"模型鉴权失败：API Key 无效、已过期，或与当前平台/Base URL 不匹配。{request_id_text}",
            401,
            True,
        )

    if "invalidendpointormodel.notfound" in lower or (
        "model or endpoint" in lower and "not found" in lower
    ):
        return (
            f"模型连接失败：模型或接口不存在，请检查 Base URL 和模型名称。{request_id_text}",
            400,
            True,
        )

    if "does not exist or you do not have access" in lower:
        return (
            f"模型连接失败：模型不存在或当前账号无访问权限。{request_id_text}",
            403,
            True,
        )

    if "rate limit" in lower or "too many requests" in lower:
        return (f"请求过于频繁，请稍后重试。{request_id_text}", 429, True)

    if "timeout" in lower or "timed out" in lower:
        return (f"模型服务请求超时，请稍后重试。{request_id_text}", 504, True)

    status_code = _extract_http_status_code(raw_message)
    if status_code is not None and 400 <= status_code <= 599:
        return (f"模型服务调用失败（HTTP {status_code}）。{request_id_text}", status_code, True)

    return raw_message, default_status, False


def _assert_within(path: Path, root: Path, field_name: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{field_name} 不在允许目录内") from exc


def _resolve_upload_filepath(raw_path: Any) -> Path:
    if not raw_path:
        raise ValueError("文件路径不能为空")
    path = Path(str(raw_path)).expanduser().resolve(strict=False)
    _assert_within(path, UPLOAD_ROOT, "filepath")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("文件不存在")
    return path


def _resolve_output_dir(raw_output_dir: Any, must_exist: bool = True) -> Path:
    if not raw_output_dir:
        raise ValueError("输出目录不能为空")
    candidate = Path(str(raw_output_dir))
    if not candidate.is_absolute():
        candidate = OUTPUT_ROOT / candidate
    output_dir = candidate.expanduser().resolve(strict=False)
    _assert_within(output_dir, OUTPUT_ROOT, "output_dir")
    if must_exist and not output_dir.exists():
        raise FileNotFoundError("输出目录不存在")
    return output_dir


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
                httponly=False,
            )
        return response


history_service = HistoryService(
    history_path=HISTORY_PATH,
    lock_obj=history_lock,
    max_history=MAX_HISTORY,
    owner_pattern=HISTORY_OWNER_PATTERN,
    owner_max_len=HISTORY_OWNER_MAX_LEN,
    owner_header=HISTORY_OWNER_HEADER,
    owner_cookie=HISTORY_OWNER_COOKIE,
    owner_cookie_max_age=HISTORY_OWNER_COOKIE_MAX_AGE,
)


def _read_history_unlocked() -> List[Dict[str, Any]]:
    return history_service.read_unlocked()


def _write_history_unlocked(history: List[Dict[str, Any]]) -> None:
    history_service.write_unlocked(history)


def _normalize_history_owner(raw_owner: Any) -> str:
    return history_service.normalize_owner(raw_owner)


def _extract_history_owner() -> str:
    return history_service.extract_owner()


def _ensure_history_owner() -> str:
    return history_service.ensure_owner()


def _record_owner(record: Dict[str, Any]) -> str:
    return history_service.record_owner(record)


def _trim_history_per_owner(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return history_service.trim_history_per_owner(history)


def _strip_owner_field(record: Dict[str, Any]) -> Dict[str, Any]:
    return history_service.strip_owner_field(record)


def load_history(owner_id: str) -> List[Dict[str, Any]]:
    return history_service.load(owner_id)


def save_history(record: Dict[str, Any], owner_id: str) -> None:
    history_service.save(record, owner_id)


def delete_history_record(record_id: str, owner_id: str) -> None:
    history_service.delete(record_id, owner_id)


@app.after_request
def attach_history_owner_cookie(response):
    return history_service.attach_owner_cookie(response)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_unique_upload_path(filename: str) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    candidate = UPLOAD_ROOT / safe_name
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while candidate.exists():
        candidate = UPLOAD_ROOT / f"{stem}_{counter}{suffix}"
        counter += 1

    return candidate


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
            return session if isinstance(session, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def save(self, upload_id: str, session: Dict[str, Any]) -> None:
        session_path = self.session_json_path(upload_id)
        tmp_path = session_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        tmp_path.replace(session_path)

    def delete(self, upload_id: str) -> None:
        self.release_memory(upload_id)
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


upload_session_service = UploadSessionService(
    session_root=UPLOAD_SESSION_ROOT,
    memory_buffers=upload_memory_buffers,
    memory_reserved_bytes=upload_memory_reserved_bytes,
    max_memory_total_bytes=UPLOAD_IN_MEMORY_MAX_TOTAL_BYTES,
    logger_obj=logger,
)


def _normalize_upload_id(raw_upload_id: Any) -> str:
    return upload_session_service.normalize_upload_id(raw_upload_id)


def _upload_session_json_path(upload_id: str) -> Path:
    return upload_session_service.session_json_path(upload_id)


def _upload_session_temp_path(upload_id: str) -> Path:
    return upload_session_service.session_temp_path(upload_id)


def _normalize_received_chunks(raw_chunks: Any, total_chunks: int) -> List[int]:
    return upload_session_service.normalize_received_chunks(raw_chunks, total_chunks)


def _load_upload_session(upload_id: str) -> Dict[str, Any] | None:
    return upload_session_service.load(upload_id)


def _save_upload_session(upload_id: str, session: Dict[str, Any]) -> None:
    upload_session_service.save(upload_id, session)


def _delete_upload_session(upload_id: str) -> None:
    global upload_memory_reserved_total_bytes
    upload_session_service.delete(upload_id)
    upload_memory_reserved_total_bytes = upload_session_service.reserved_total_bytes


def _reserve_upload_memory(upload_id: str, total_size: int) -> bool:
    global upload_memory_reserved_total_bytes
    reserved = upload_session_service.reserve_memory(upload_id, total_size)
    upload_memory_reserved_total_bytes = upload_session_service.reserved_total_bytes
    return reserved


def _release_upload_memory(upload_id: str) -> None:
    global upload_memory_reserved_total_bytes
    upload_session_service.release_memory(upload_id)
    upload_memory_reserved_total_bytes = upload_session_service.reserved_total_bytes


def _get_chunk_storage_mode(session: Dict[str, Any]) -> str:
    return upload_session_service.get_chunk_storage_mode(session)


def _create_unique_output_dir(video_path: Path) -> Path:
    base_name = secure_filename(video_path.stem) or "video"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = OUTPUT_ROOT / f"{base_name}_{timestamp}"
    counter = 1

    while candidate.exists():
        candidate = OUTPUT_ROOT / f"{base_name}_{timestamp}_{counter}"
        counter += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _normalize_risk_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def _risk_decision_rank(decision: str) -> int:
    order = {"allow": 0, "restrict": 1, "block": 2}
    return order.get(str(decision or "").strip().lower(), 0)


def _risk_decision_from_rank(rank: int) -> str:
    if rank >= 2:
        return "block"
    if rank <= 0:
        return "allow"
    return "restrict"


def _risk_level_from_decision(decision: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized == "block":
        return "high"
    if normalized == "restrict":
        return "medium"
    return "low"


def _resolve_risk_frame_count(max_frames: int, video_duration_seconds: float | None) -> int:
    base_count = _safe_int(max_frames, RISK_MAX_FRAMES, RISK_MIN_FRAMES, RISK_DYNAMIC_MAX_FRAMES)
    if video_duration_seconds is None or video_duration_seconds <= 0:
        return base_count

    growth_source = max(0.0, float(video_duration_seconds) - RISK_FRAME_GROWTH_START_SECONDS)
    bonus_frames = int(growth_source // RISK_FRAME_GROWTH_EVERY_SECONDS)
    return _safe_int(
        base_count + bonus_frames,
        base_count,
        RISK_MIN_FRAMES,
        RISK_DYNAMIC_MAX_FRAMES,
    )


def _stable_risk_sampling_seed(
    video_path: Path | None, video_duration_seconds: float | None, frame_count: int
) -> int:
    path_text = str(video_path or "")
    size = 0
    mtime_ns = 0
    if video_path is not None:
        try:
            stat_info = video_path.stat()
            size = int(getattr(stat_info, "st_size", 0))
            mtime_ns = int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1e9)))
        except OSError:
            pass
    duration_text = "none" if video_duration_seconds is None else f"{float(video_duration_seconds):.3f}"
    seed_text = f"{path_text}|{size}|{mtime_ns}|{duration_text}|{frame_count}"
    digest = hashlib.sha256(seed_text.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:16], 16)


def _probe_video_duration_seconds(video_path: Path, ffmpeg_cmd: str = "ffmpeg") -> float | None:
    ffprobe_candidates: List[str] = ["ffprobe"]
    ffmpeg_text = str(ffmpeg_cmd or "").strip()
    if ffmpeg_text:
        ffmpeg_path = Path(ffmpeg_text)
        if ffmpeg_path.is_absolute():
            suffix = ffmpeg_path.suffix.lower()
            ffprobe_name = "ffprobe.exe" if suffix == ".exe" else "ffprobe"
            ffprobe_candidates.insert(0, str(ffmpeg_path.with_name(ffprobe_name)))

    seen: set[str] = set()
    for ffprobe_cmd in ffprobe_candidates:
        cmd_text = str(ffprobe_cmd or "").strip()
        if not cmd_text or cmd_text in seen:
            continue
        seen.add(cmd_text)
        try:
            result = subprocess.run(
                [
                    cmd_text,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=18,
            )
        except Exception:
            continue

        raw_output = (result.stdout or "").strip()
        if not raw_output:
            continue
        try:
            duration = float(raw_output)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration

    try:
        fallback = subprocess.run(
            [ffmpeg_text or "ffmpeg", "-i", str(video_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=18,
        )
        probe_text = f"{fallback.stdout or ''}\n{fallback.stderr or ''}"
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_text)
        if not match:
            return None
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        duration = hours * 3600 + minutes * 60 + seconds
        return duration if duration > 0 else None
    except Exception:
        return None


def _build_risk_timestamps(
    max_frames: int,
    *,
    video_duration_seconds: float | None = None,
    video_path: Path | None = None,
) -> List[int]:
    frame_count = _resolve_risk_frame_count(max_frames, video_duration_seconds)
    if video_duration_seconds is None or video_duration_seconds <= 0:
        base = [0, 2, 5, 10, 15, 25, 35, 50, 70, 95, 125, 160, 200, 245, 295]
        return base[:frame_count]

    max_second = max(1, int(video_duration_seconds) - 1)
    seed = _stable_risk_sampling_seed(video_path, video_duration_seconds, frame_count)
    rng = random.Random(seed)

    timestamps: List[int] = []
    for idx in range(frame_count):
        segment_start = int((idx * max_second) / frame_count)
        segment_end = int(((idx + 1) * max_second) / frame_count)
        if idx == frame_count - 1:
            segment_end = max_second
        if segment_end < segment_start:
            segment_end = segment_start
        if segment_end == segment_start:
            sample = segment_start
        else:
            sample = rng.randint(segment_start, segment_end)
        timestamps.append(sample)

    unique_sorted = sorted(set(max(0, min(max_second, int(ts))) for ts in timestamps))
    while len(unique_sorted) < frame_count:
        candidate = rng.randint(0, max_second)
        if candidate in unique_sorted:
            continue
        unique_sorted.append(candidate)
        unique_sorted.sort()

    return unique_sorted[:frame_count]


def _is_image_input_not_supported_error(error: Any) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    image_tokens = ("image_url", "image input", "vision", "multimodal", "multi-modal")
    unsupported_tokens = (
        "not support",
        "unsupported",
        "only supported",
        "does not support",
        "invalid content type",
        "not allowed",
    )
    has_image_hint = any(token in text for token in image_tokens)
    has_unsupported_hint = any(token in text for token in unsupported_tokens)
    return has_image_hint and has_unsupported_hint


def _normalize_risk_keyword_text(raw_text: str) -> str:
    text = str(raw_text or "").lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _count_keyword_hits(
    text: str, explicit_keywords: List[str], medium_keywords: List[str]
) -> Tuple[int, int, List[str]]:
    hit_keywords: List[str] = []
    explicit_hits = 0
    medium_hits = 0

    for keyword in explicit_keywords:
        if keyword and keyword in text:
            explicit_hits += 1
            if len(hit_keywords) < 6:
                hit_keywords.append(keyword)
    for keyword in medium_keywords:
        if keyword and keyword in text:
            medium_hits += 1
            if len(hit_keywords) < 6 and keyword not in hit_keywords:
                hit_keywords.append(keyword)
    return explicit_hits, medium_hits, hit_keywords


def _default_text_risk_keyword_lexicon() -> Dict[str, Dict[str, Any]]:
    # Keep a minimal in-code schema fallback.
    # The runtime source of truth should be risk_keyword_lexicon.json.
    return {
        "nudity": {
            "explicit": [],
            "medium": [],
            "reason_code_high": "EXPLICIT_PORNOGRAPHIC_CONTENT",
            "reason_code_medium": "POTENTIAL_PORNOGRAPHIC_CONTENT",
            "reason_label": "色情/裸露",
        },
        "violence": {
            "explicit": [],
            "medium": [],
            "reason_code_high": "SEVERE_VIOLENCE_CONTENT",
            "reason_code_medium": "POTENTIAL_VIOLENCE_CONTENT",
            "reason_label": "暴力",
        },
        "gore": {
            "explicit": [],
            "medium": [],
            "reason_code_high": "GORE_CONTENT",
            "reason_code_medium": "POTENTIAL_GORE_CONTENT",
            "reason_label": "血腥",
        },
    }


def _normalize_text_risk_keyword_list(raw_keywords: Any) -> List[str]:
    if not isinstance(raw_keywords, list):
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for item in raw_keywords:
        keyword = str(item or "").strip().lower()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)
    return normalized


def _normalize_text_risk_reason_code(raw_code: Any, fallback: str) -> str:
    code = re.sub(r"[^A-Z0-9_]+", "_", str(raw_code or "").strip().upper()).strip("_")
    return code or fallback


def _normalize_text_risk_keyword_lexicon(
    loaded: Any, defaults: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    source = loaded if isinstance(loaded, dict) else {}
    normalized: Dict[str, Dict[str, Any]] = {}

    for dimension in ("nudity", "violence", "gore"):
        default_item = defaults[dimension]
        source_item = source.get(dimension, {})
        source_dict = source_item if isinstance(source_item, dict) else {}

        explicit_keywords = _normalize_text_risk_keyword_list(source_dict.get("explicit"))
        medium_keywords = _normalize_text_risk_keyword_list(source_dict.get("medium"))
        reason_code_high = _normalize_text_risk_reason_code(
            source_dict.get("reason_code_high"), str(default_item["reason_code_high"])
        )
        reason_code_medium = _normalize_text_risk_reason_code(
            source_dict.get("reason_code_medium"), str(default_item["reason_code_medium"])
        )
        reason_label = str(source_dict.get("reason_label", "")).strip() or str(
            default_item["reason_label"]
        )

        normalized[dimension] = {
            "explicit": explicit_keywords,
            "medium": medium_keywords,
            "reason_code_high": reason_code_high,
            "reason_code_medium": reason_code_medium,
            "reason_label": reason_label,
        }

    return normalized


def _load_text_risk_keyword_lexicon() -> Dict[str, Dict[str, Any]]:
    global risk_keyword_lexicon_cache_mtime_ns, risk_keyword_lexicon_cache_data

    defaults = _default_text_risk_keyword_lexicon()
    lexicon_path = RISK_KEYWORD_LEXICON_PATH

    try:
        stat_info = lexicon_path.stat()
        current_mtime_ns = int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1e9)))
    except OSError:
        logger.warning("字幕关键词风控词库文件不存在，已使用空词库默认配置: %s", lexicon_path)
        return defaults

    with risk_keyword_lexicon_lock:
        if (
            risk_keyword_lexicon_cache_data is not None
            and risk_keyword_lexicon_cache_mtime_ns == current_mtime_ns
        ):
            return risk_keyword_lexicon_cache_data

        try:
            with open(lexicon_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            merged = _normalize_text_risk_keyword_lexicon(loaded, defaults)
        except Exception as exc:
            logger.warning("加载字幕关键词风控词库失败，已使用空词库默认配置: %s", exc)
            merged = defaults

        risk_keyword_lexicon_cache_mtime_ns = current_mtime_ns
        risk_keyword_lexicon_cache_data = merged
        return merged


def _build_text_fallback_risk_result(
    combined_text: str, subtitle_text: str, filename_text: str
) -> Dict[str, Any]:
    keyword_groups = _load_text_risk_keyword_lexicon()

    dimensions: Dict[str, Dict[str, Any]] = {}
    scores: Dict[str, float] = {}
    fallback_evidence: Dict[str, Any] = {"subtitle_used": bool(subtitle_text), "filename_used": bool(filename_text)}

    for key, config in keyword_groups.items():
        explicit_hits, medium_hits, hit_keywords = _count_keyword_hits(
            combined_text, config["explicit"], config["medium"]
        )
        subtitle_explicit_hits, subtitle_medium_hits, _ = _count_keyword_hits(
            subtitle_text, config["explicit"], config["medium"]
        )
        filename_explicit_hits, filename_medium_hits, _ = _count_keyword_hits(
            filename_text, config["explicit"], config["medium"]
        )

        score = min(
            1.0,
            explicit_hits * 0.36
            + medium_hits * 0.12
            + filename_explicit_hits * 0.25
            + filename_medium_hits * 0.1,
        )
        scores[key] = round(score, 3)
        dimensions[key] = {
            "score": scores[key],
            "label": "explicit" if explicit_hits > 0 else ("mild" if medium_hits > 0 else "none"),
            "evidence": ", ".join(hit_keywords[:4]),
            "subtitle_hits": subtitle_explicit_hits + subtitle_medium_hits,
            "filename_hits": filename_explicit_hits + filename_medium_hits,
        }

    max_dimension = max(scores, key=scores.get) if scores else "nudity"
    max_score = scores.get(max_dimension, 0.0)
    decision = "allow"
    if max_score >= TEXT_RISK_BLOCK_THRESHOLD:
        decision = "block"
    elif max_score >= TEXT_RISK_RESTRICT_THRESHOLD:
        decision = "restrict"

    risk_level = "low"
    if decision == "block":
        risk_level = "high"
    elif decision == "restrict":
        risk_level = "medium"

    selected_group = keyword_groups[max_dimension]
    reason_code = "TEXT_SAFE_CONTENT"
    if decision == "block":
        reason_code = str(selected_group["reason_code_high"])
    elif decision == "restrict":
        reason_code = str(selected_group["reason_code_medium"])

    if decision == "allow":
        reason = "未在字幕/文件名中检测到明显黄暴血腥关键词。"
    else:
        reason = (
            f"字幕关键词风控检测到{selected_group['reason_label']}相关高风险线索，已触发{risk_level}拦截策略。"
        )

    hit_total = sum(
        int(dimensions[item].get("subtitle_hits", 0)) + int(dimensions[item].get("filename_hits", 0))
        for item in dimensions
    )
    confidence = min(0.95, 0.45 + hit_total * 0.07)

    return {
        "decision": decision,
        "risk_level": risk_level,
        "reason_code": reason_code,
        "reason": reason,
        "confidence": round(confidence, 3),
        "scores": scores,
        "dimensions": dimensions,
        "frame_count": 0,
        "fallback_mode": "subtitle_keyword_risk_gate",
        "fallback_evidence": fallback_evidence,
    }


def _run_text_fallback_risk_gate(
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    *,
    strict_on_insufficient_signal: bool = True,
    fallback_mode: str = "subtitle_keyword_risk_gate",
    subtitle_cache_identity: str = "",
) -> Dict[str, Any]:
    subtitle_dir = output_dir / ".risk_subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    subtitle_text = ""
    filename_text = _normalize_risk_keyword_text(video_path.name)
    try:
        srt_path = agent.generate_subtitles(
            str(video_path),
            str(subtitle_dir),
            cache_identity=subtitle_cache_identity or None,
        )
        subtitles = agent.parse_srt(srt_path)
        subtitle_text = _normalize_risk_keyword_text(
            "\n".join(str(item.get("text", "")).strip() for item in subtitles if item.get("text"))
        )
    except Exception as exc:
        logger.warning("Text fallback subtitle generation failed: %s", exc)
    finally:
        shutil.rmtree(subtitle_dir, ignore_errors=True)

    combined_text = " ".join(part for part in [subtitle_text, filename_text] if part).strip()
    if not combined_text:
        if strict_on_insufficient_signal:
            return {
                "decision": "block",
                "risk_level": "high",
                "reason_code": "TEXT_RISK_SIGNAL_INSUFFICIENT",
                "reason": "视觉模型不支持图片输入，且字幕关键词信号不足，已按高风险默认拒绝上传。",
                "confidence": 0.62,
                "scores": {"nudity": 0.0, "violence": 0.0, "gore": 0.0},
                "dimensions": {},
                "frame_count": 0,
                "fallback_mode": fallback_mode,
                "fallback_evidence": {"subtitle_used": False, "filename_used": bool(filename_text)},
            }
        return {
            "decision": "allow",
            "risk_level": "low",
            "reason_code": "TEXT_RISK_SIGNAL_INSUFFICIENT",
            "reason": "字幕关键词信号不足，文本兜底链路不单独触发拦截。",
            "confidence": 0.35,
            "scores": {"nudity": 0.0, "violence": 0.0, "gore": 0.0},
            "dimensions": {},
            "frame_count": 0,
            "fallback_mode": fallback_mode,
            "fallback_evidence": {"subtitle_used": False, "filename_used": bool(filename_text)},
            "fallback_non_strict": True,
        }
    result = _build_text_fallback_risk_result(combined_text, subtitle_text, filename_text)
    result["fallback_mode"] = fallback_mode
    if not strict_on_insufficient_signal:
        result["fallback_non_strict"] = True
    return result


def _sample_risk_frames(
    agent: VideoAnalyzerAgent, video_path: Path, output_dir: Path, max_frames: int
) -> Tuple[List[Path], Path]:
    frame_dir = output_dir / ".risk_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: List[Path] = []
    video_duration_seconds = _probe_video_duration_seconds(
        video_path,
        str(getattr(agent, "ffmpeg_cmd", "")).strip() or "ffmpeg",
    )
    timestamps = _build_risk_timestamps(
        max_frames,
        video_duration_seconds=video_duration_seconds,
        video_path=video_path,
    )
    logger.info(
        "Risk gate sampling: duration=%.2fs, frames=%s, timestamps=%s",
        float(video_duration_seconds or 0.0),
        len(timestamps),
        timestamps,
    )
    for idx, second in enumerate(timestamps, start=1):
        frame_path = agent.generate_screenshot(video_path, frame_dir, second, step_num=idx)
        if frame_path is not None and frame_path.exists():
            frame_paths.append(frame_path)
    return frame_paths, frame_dir


def _build_env_visual_fallback_agent(primary_agent: VideoAnalyzerAgent) -> VideoAnalyzerAgent | None:
    api_key, model_name, model_base_url = _read_risk_fallback_env_model_options()
    if not api_key or not model_name:
        return None

    primary_api_key = str(getattr(primary_agent, "api_key", "")).strip()
    primary_model_name = str(getattr(primary_agent, "model", "")).strip()
    primary_base_url = str(getattr(primary_agent, "base_url", "")).strip()
    normalized_base_url = model_base_url or DEFAULT_MODEL_BASE_URL

    # Skip meaningless self-fallback to the exact same visual model config.
    if (
        api_key == primary_api_key
        and model_name == primary_model_name
        and normalized_base_url == primary_base_url
    ):
        return None

    try:
        return VideoAnalyzerAgent(
            api_key=api_key,
            whisper_model="base",
            model_name=model_name,
            model_base_url=normalized_base_url,
        )
    except Exception as exc:
        logger.warning("系统级视觉风控兜底模型初始化失败: %s", exc)
        return None


def _try_env_visual_risk_fallback(
    primary_agent: VideoAnalyzerAgent, frame_paths: List[Path]
) -> Tuple[Dict[str, Any] | None, str]:
    env_agent = _build_env_visual_fallback_agent(primary_agent)
    if env_agent is None:
        return None, "ENV_VISUAL_FALLBACK_NOT_READY"

    try:
        raw = _run_async(_request_risk_decision(env_agent, frame_paths))
        normalized = _normalize_risk_result(
            raw if isinstance(raw, dict) else {}, frame_count=len(frame_paths)
        )
        normalized["fallback_mode"] = "env_visual_model_risk_gate"
        normalized["fallback_visual_model"] = str(getattr(env_agent, "model", "")).strip()
        normalized["fallback_visual_base_url"] = str(getattr(env_agent, "base_url", "")).strip()
        return normalized, ""
    except Exception as exc:
        error_message, status_code, _ = _normalize_provider_error(exc, default_status=500)
        return None, f"{error_message} (status={status_code})"


def _run_text_fallback_after_visual_unavailable(
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    reason_code: str,
    reason_suffix: str,
    provider_status: int | None = None,
    provider_error: str = "",
    env_visual_error: str = "",
    prefetched_text_risk: Dict[str, Any] | None = None,
    subtitle_cache_identity: str = "",
) -> Dict[str, Any]:
    fallback: Dict[str, Any]
    if isinstance(prefetched_text_risk, dict):
        fallback = dict(prefetched_text_risk)
        fallback.pop("fallback_non_strict", None)
        fallback["fallback_mode"] = "subtitle_keyword_risk_gate"

        prefetched_reason_code = str(fallback.get("reason_code", "")).strip().upper()
        prefetched_decision = str(fallback.get("decision", "")).strip().lower()
        if (
            prefetched_decision == "allow"
            and prefetched_reason_code == "TEXT_RISK_SIGNAL_INSUFFICIENT"
        ):
            existing_evidence = fallback.get("fallback_evidence", {})
            filename_used = (
                bool(existing_evidence.get("filename_used", False))
                if isinstance(existing_evidence, dict)
                else False
            )
            fallback.update(
                {
                    "decision": "block",
                    "risk_level": "high",
                    "reason_code": "TEXT_RISK_SIGNAL_INSUFFICIENT",
                    "reason": "视觉模型不支持图片输入，且字幕关键词信号不足，已按高风险默认拒绝上传。",
                    "confidence": 0.62,
                    "scores": {"nudity": 0.0, "violence": 0.0, "gore": 0.0},
                    "dimensions": {},
                    "frame_count": 0,
                    "fallback_mode": "subtitle_keyword_risk_gate",
                    "fallback_evidence": {
                        "subtitle_used": False,
                        "filename_used": filename_used,
                    },
                }
            )
    else:
        fallback = _run_text_fallback_risk_gate(
            agent,
            video_path,
            output_dir,
            subtitle_cache_identity=subtitle_cache_identity,
        )

    fallback["reason_code"] = str(fallback.get("reason_code", "")).strip() or reason_code
    base_reason = str(fallback.get("reason", "")).strip()
    if base_reason:
        fallback["reason"] = f"{base_reason}（{reason_suffix}）"
    else:
        fallback["reason"] = reason_suffix
    fallback["visual_fallback_attempted"] = True
    if provider_status is not None:
        fallback["provider_status"] = provider_status
    if provider_error:
        fallback["provider_error"] = provider_error
    if env_visual_error:
        fallback["fallback_visual_error"] = env_visual_error
    return fallback


def _apply_text_secondary_risk_gate_when_visual_available(
    primary_risk: Dict[str, Any],
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    text_risk: Dict[str, Any] | None = None,
    subtitle_cache_identity: str = "",
) -> Dict[str, Any]:
    merged = dict(primary_risk)
    if not isinstance(text_risk, dict):
        text_risk = _run_text_fallback_risk_gate(
            agent=agent,
            video_path=video_path,
            output_dir=output_dir,
            strict_on_insufficient_signal=False,
            fallback_mode="subtitle_keyword_secondary_gate",
            subtitle_cache_identity=subtitle_cache_identity,
        )

    primary_decision = str(merged.get("decision", "allow")).strip().lower()
    text_decision = str(text_risk.get("decision", "allow")).strip().lower()
    merged["text_fallback_applied"] = True
    merged["text_fallback_mode"] = "subtitle_keyword_secondary_gate"
    merged["text_fallback_risk"] = {
        "decision": text_decision,
        "risk_level": str(text_risk.get("risk_level", _risk_level_from_decision(text_decision))),
        "reason_code": str(text_risk.get("reason_code", "")),
        "reason": str(text_risk.get("reason", "")),
        "confidence": text_risk.get("confidence", 0.0),
    }

    if _risk_decision_rank(text_decision) <= _risk_decision_rank(primary_decision):
        merged["text_fallback_override"] = False
        return merged

    text_reason = str(text_risk.get("reason", "")).strip()
    merged["decision"] = text_decision
    merged["risk_level"] = str(text_risk.get("risk_level", "")).strip().lower() or _risk_level_from_decision(
        text_decision
    )
    merged["reason_code"] = str(text_risk.get("reason_code", "")).strip() or "TEXT_RISK_SECONDARY_GATE"
    merged["reason"] = (
        f"{text_reason}（视觉模型可用，字幕关键词兜底链路触发更严格策略）"
        if text_reason
        else "视觉模型可用，字幕关键词兜底链路触发更严格策略。"
    )
    merged["confidence"] = _normalize_risk_score(
        text_risk.get("confidence", merged.get("confidence", 0.6)),
        _normalize_risk_score(merged.get("confidence", 0.6), 0.6),
    )
    if isinstance(text_risk.get("scores"), dict):
        merged["scores"] = text_risk.get("scores", {})
    if isinstance(text_risk.get("dimensions"), dict):
        merged["dimensions"] = text_risk.get("dimensions", {})
    merged["text_fallback_override"] = True
    return merged


def _normalize_risk_result(raw_result: Dict[str, Any], frame_count: int) -> Dict[str, Any]:
    dimensions: Dict[str, Dict[str, Any]] = {}
    for key in ("nudity", "violence", "gore"):
        section = raw_result.get(key, {})
        if isinstance(section, dict):
            score = _normalize_risk_score(section.get("score", section.get("probability", 0.0)))
            label = str(section.get("label", "") or "").strip().lower()
            evidence = str(section.get("evidence", section.get("reason", "")) or "").strip()
        else:
            score = _normalize_risk_score(section, 0.0)
            label = ""
            evidence = ""
        dimensions[key] = {"score": score, "label": label, "evidence": evidence[:180]}

    scores = {key: dimensions[key]["score"] for key in dimensions}
    max_dimension = max(scores, key=scores.get) if scores else "nudity"
    max_score = scores.get(max_dimension, 0.0)
    has_explicit_or_severe_label = any(
        str(dimensions.get(key, {}).get("label", "")).lower() in {"explicit", "severe"}
        and float(dimensions.get(key, {}).get("score", 0.0)) >= 0.45
        for key in dimensions
    )
    has_hard_block_score = any(
        float(dimensions.get(key, {}).get("score", 0.0)) >= RISK_DIMENSION_HARD_BLOCK_SCORE
        for key in dimensions
    )
    has_critical_score = any(
        float(dimensions.get(key, {}).get("score", 0.0)) >= RISK_CRITICAL_SCORE
        for key in dimensions
    )
    model_reason_code = str(raw_result.get("reason_code", "") or "").strip().upper()
    has_hard_block_reason_code = model_reason_code in {
        "EXPLICIT_PORNOGRAPHIC_CONTENT",
        "SEVERE_VIOLENCE_CONTENT",
        "GORE_CONTENT",
        "SEXUAL_VIOLENCE_CONTENT",
    } or model_reason_code.endswith("_HIGH")
    has_hard_block_evidence = (
        has_explicit_or_severe_label
        or has_hard_block_score
        or has_critical_score
        or has_hard_block_reason_code
    )

    score_based_decision = "allow"
    if max_score >= RISK_BLOCK_THRESHOLD:
        score_based_decision = "block"
    elif max_score >= RISK_RESTRICT_THRESHOLD:
        score_based_decision = "restrict"
    if has_hard_block_evidence:
        score_based_decision = "block"

    decision = str(raw_result.get("decision", "") or "").strip().lower()
    if decision not in {"allow", "restrict", "block"}:
        decision = score_based_decision
    else:
        # Use the stricter result between model text decision and numeric evidence.
        decision = _risk_decision_from_rank(
            max(_risk_decision_rank(decision), _risk_decision_rank(score_based_decision))
        )

    confidence = _normalize_risk_score(raw_result.get("confidence", 0.6), 0.6)
    # Keep strict blocking when hard evidence exists; only mild low-confidence results may downgrade.
    if confidence < 0.35 and not has_hard_block_evidence:
        if decision == "restrict":
            decision = "allow"

    risk_level = str(raw_result.get("risk_level", "") or "").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        if decision == "block":
            risk_level = "high"
        elif decision == "restrict":
            risk_level = "medium"
        else:
            risk_level = "low"

    reason_code = str(raw_result.get("reason_code", "") or "").strip().upper()
    if not reason_code:
        if decision == "allow":
            reason_code = "SAFE_CONTENT"
        elif decision == "restrict":
            reason_code = f"{max_dimension.upper()}_MEDIUM"
        else:
            reason_code = f"{max_dimension.upper()}_HIGH"

    reason = str(raw_result.get("reason", "") or "").strip()
    if not reason:
        if decision == "allow":
            reason = "No high-risk nudity, violence, or gore was detected."
        elif decision == "restrict":
            reason = "Potentially sensitive content was detected."
        else:
            reason = "High-risk sensitive content was detected."

    return {
        "decision": decision,
        "risk_level": risk_level,
        "reason_code": reason_code,
        "reason": reason,
        "confidence": confidence,
        "scores": scores,
        "dimensions": dimensions,
        "frame_count": frame_count,
    }


async def _request_risk_decision(
    agent: VideoAnalyzerAgent, frame_paths: List[Path]
) -> Dict[str, Any]:
    prompt_schema = {
        "nudity": {"score": 0.0, "label": "none|mild|explicit", "evidence": ""},
        "violence": {"score": 0.0, "label": "none|mild|severe", "evidence": ""},
        "gore": {"score": 0.0, "label": "none|mild|severe", "evidence": ""},
        "decision": "allow|restrict|block",
        "risk_level": "low|medium|high",
        "confidence": 0.0,
        "reason_code": "UPPER_SNAKE_CASE",
        "reason": "short explanation",
    }
    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "You are a video safety moderator. "
                "Classify nudity, violence, and gore from the provided frames. "
                "Use block only when clear, explicit high-risk evidence exists. "
                "If uncertain, keep scores conservative and explain uncertainty. "
                f"Return JSON only with this schema: {json.dumps(prompt_schema, ensure_ascii=False)}"
            ),
        }
    ]

    for frame_path in frame_paths:
        with open(frame_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
            }
        )

    result = await agent._chat_completion_text(
        [
            {
                "role": "system",
                "content": "You are a content safety classifier for nudity, violence, and gore.",
            },
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
    )
    parsed = agent._parse_json_object_response(result)
    return parsed if isinstance(parsed, dict) else {}


def _run_video_risk_gate(
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    subtitle_cache_identity: str = "",
) -> Tuple[Dict[str, Any], Path]:
    frame_paths, frame_dir = _sample_risk_frames(
        agent=agent,
        video_path=video_path,
        output_dir=output_dir,
        max_frames=RISK_MAX_FRAMES,
    )
    if not frame_paths:
        logger.warning(
            "Risk gate frame extraction failed, fallback to subtitle keyword gate: %s",
            video_path,
        )
        fallback = _run_text_fallback_risk_gate(
            agent,
            video_path,
            output_dir,
            subtitle_cache_identity=subtitle_cache_identity,
        )
        fallback["reason_code"] = (
            str(fallback.get("reason_code", "")).strip() or "TEXT_RISK_FRAME_FALLBACK"
        )
        fallback["reason"] = (
            f"{str(fallback.get('reason', '')).strip()}（视觉帧提取失败，已自动启用字幕关键词风控兜底）"
        )
        fallback["frame_count"] = 0
        return fallback, frame_dir

    secondary_text_executor: ThreadPoolExecutor | None = None
    secondary_text_future = None
    prefetched_secondary_text_risk: Dict[str, Any] | None = None
    prefetched_secondary_loaded = False

    def _get_prefetched_secondary_text_risk() -> Dict[str, Any] | None:
        nonlocal prefetched_secondary_loaded, prefetched_secondary_text_risk
        if prefetched_secondary_loaded:
            return prefetched_secondary_text_risk
        prefetched_secondary_loaded = True
        if secondary_text_future is None:
            return None
        try:
            candidate = secondary_text_future.result()
            if isinstance(candidate, dict):
                prefetched_secondary_text_risk = dict(candidate)
        except Exception as exc:
            logger.warning("Secondary text fallback precompute failed, fallback to sync mode: %s", exc)
            prefetched_secondary_text_risk = None
        return prefetched_secondary_text_risk

    try:
        secondary_text_executor = ThreadPoolExecutor(max_workers=1)
        secondary_text_future = secondary_text_executor.submit(
            _run_text_fallback_risk_gate,
            agent,
            video_path,
            output_dir,
            strict_on_insufficient_signal=False,
            fallback_mode="subtitle_keyword_secondary_gate",
            subtitle_cache_identity=subtitle_cache_identity,
        )

        try:
            raw = _run_async(_request_risk_decision(agent, frame_paths))
            normalized = _normalize_risk_result(
                raw if isinstance(raw, dict) else {}, frame_count=len(frame_paths)
            )
            normalized = _apply_text_secondary_risk_gate_when_visual_available(
                primary_risk=normalized,
                agent=agent,
                video_path=video_path,
                output_dir=output_dir,
                text_risk=_get_prefetched_secondary_text_risk(),
                subtitle_cache_identity=subtitle_cache_identity,
            )
            return normalized, frame_dir
        except Exception as exc:
            provider_status: int | None = None
            provider_error = ""
            reason_code = "TEXT_RISK_MODEL_FALLBACK"
            reason_suffix = (
                "视觉风控服务暂不可用，已优先尝试系统级视觉兜底模型，"
                "兜底模型不可用后自动启用字幕关键词风控兜底。"
            )

            if _is_image_input_not_supported_error(exc):
                logger.warning(
                    "Risk gate model does not support image input, trying system env visual fallback first: %s",
                    exc,
                )
                provider_error = str(exc or "").strip() or "visual_input_not_supported"
                reason_code = "TEXT_RISK_FALLBACK"
                reason_suffix = (
                    "主视觉风控模型不支持图片输入，已优先尝试系统级视觉兜底模型，"
                    "兜底模型不可用后自动启用字幕关键词风控兜底。"
                )
            else:
                error_message, status_code, _ = _normalize_provider_error(
                    exc, default_status=500
                )
                provider_status = status_code
                provider_error = error_message
                logger.warning(
                    "Risk gate visual check unavailable, trying system env visual fallback first: status=%s error=%s",
                    status_code,
                    error_message,
                )
                if status_code in {400, 401, 403}:
                    reason_code = "TEXT_RISK_VISUAL_MODEL_UNAVAILABLE"
                    reason_suffix = (
                        "主视觉风控模型当前不可用（鉴权/配置受限），已优先尝试系统级视觉兜底模型，"
                        "兜底模型不可用后自动启用字幕关键词风控兜底。"
                    )

            env_visual_result, env_visual_error = _try_env_visual_risk_fallback(agent, frame_paths)
            if env_visual_result is not None:
                base_reason = str(env_visual_result.get("reason", "")).strip()
                env_visual_result["reason"] = (
                    f"{base_reason}（主视觉风控不可用，已自动切换到系统级视觉兜底模型）"
                    if base_reason
                    else "主视觉风控不可用，已自动切换到系统级视觉兜底模型。"
                )
                env_visual_result["visual_fallback_attempted"] = True
                if provider_status is not None:
                    env_visual_result["provider_status"] = provider_status
                if provider_error:
                    env_visual_result["provider_error"] = provider_error
                env_visual_result = _apply_text_secondary_risk_gate_when_visual_available(
                    primary_risk=env_visual_result,
                    agent=agent,
                    video_path=video_path,
                    output_dir=output_dir,
                    text_risk=_get_prefetched_secondary_text_risk(),
                    subtitle_cache_identity=subtitle_cache_identity,
                )
                return env_visual_result, frame_dir

            logger.warning(
                "System env visual fallback unavailable, switch to subtitle keyword risk fallback: %s",
                env_visual_error,
            )
            fallback = _run_text_fallback_after_visual_unavailable(
                agent=agent,
                video_path=video_path,
                output_dir=output_dir,
                reason_code=reason_code,
                reason_suffix=reason_suffix,
                provider_status=provider_status,
                provider_error=provider_error,
                env_visual_error=env_visual_error,
                prefetched_text_risk=_get_prefetched_secondary_text_risk(),
                subtitle_cache_identity=subtitle_cache_identity,
            )
            return fallback, frame_dir
    finally:
        if secondary_text_executor is not None:
            secondary_text_executor.shutdown(wait=False, cancel_futures=True)


def _reason_code_slug(reason_code: str) -> str:
    slug = secure_filename(str(reason_code or "").strip().lower()).replace("-", "_")
    return slug or "content_policy"


def _quarantine_upload_file(video_path: Path, reason_code: str) -> Path | None:
    try:
        resolved = video_path.resolve(strict=False)
        _assert_within(resolved, UPLOAD_ROOT, "filepath")
    except ValueError:
        return None

    if not resolved.exists() or not resolved.is_file():
        return None

    reason_dir = QUARANTINE_ROOT / _reason_code_slug(reason_code)
    reason_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = reason_dir / f"{resolved.stem}_{timestamp}{resolved.suffix}"
    counter = 1
    while target.exists():
        target = reason_dir / f"{resolved.stem}_{timestamp}_{counter}{resolved.suffix}"
        counter += 1

    try:
        shutil.move(str(resolved), str(target))
        return target
    except OSError as exc:
        logger.warning("Failed to quarantine blocked video: %s", exc)
        return None


def _should_block_by_risk(decision: str) -> bool:
    return decision == "block" or (decision == "restrict" and RISK_BLOCK_ON_RESTRICT)


def _build_upload_staging_path(filename: str) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = f"staging_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    suffix = Path(safe_name).suffix or ".mp4"
    stem = Path(safe_name).stem or "staging"
    candidate = UPLOAD_STAGING_ROOT / f"{stem}_{uuid4().hex[:10]}{suffix}"
    _assert_within(candidate.resolve(strict=False), UPLOAD_STAGING_ROOT, "staging_path")
    return candidate


def _safe_remove_file(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        logger.warning("删除文件失败: %s", path)


class UploadRiskService:
    def resolve_upload_risk_api_key(self) -> str:
        # Fallback chain when no upload-time key is provided by the caller.
        for key_name in ("RISK_API_KEY", "MODEL_API_KEY", "ARK_API_KEY", "OPENAI_API_KEY"):
            value = str(os.getenv(key_name, "")).strip()
            if value:
                return value
        return ""

    def upload_risk_unavailable_message(self) -> str:
        return (
            "上传风控服务不可用，已拒绝上传。"
            "请前往设置检查 API Key、模型名称与模型接口配置后重试上传。"
        )

    def upload_risk_unavailable_payload(self) -> Dict[str, Any]:
        return {
            "error": self.upload_risk_unavailable_message(),
            "code": "risk_service_unavailable",
        }

    def build_risk_agent_for_upload(
        self, api_key: str = "", model_name: str = "", model_base_url: str = ""
    ) -> VideoAnalyzerAgent:
        risk_api_key = str(api_key or "").strip() or self.resolve_upload_risk_api_key()
        if not risk_api_key:
            raise ValueError("上传风控模型 API Key 未配置")

        risk_model_name = (
            str(model_name or "").strip()
            or str(os.getenv("RISK_MODEL_NAME", "")).strip()
            or DEFAULT_MODEL_NAME
        )
        risk_model_base_url = (
            str(model_base_url or "").strip()
            or str(os.getenv("RISK_MODEL_BASE_URL", "")).strip()
            or DEFAULT_MODEL_BASE_URL
        )
        return VideoAnalyzerAgent(
            api_key=risk_api_key,
            whisper_model="base",
            model_name=risk_model_name,
            model_base_url=risk_model_base_url,
        )

    def moderate_staged_upload(
        self,
        staged_video_path: Path,
        risk_agent: VideoAnalyzerAgent,
        file_fingerprint: str = "",
    ) -> Dict[str, Any]:
        output_dir = _create_unique_output_dir(staged_video_path)
        try:
            risk, _ = _run_video_risk_gate(
                risk_agent,
                staged_video_path,
                output_dir,
                subtitle_cache_identity=file_fingerprint,
            )
            return risk
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def risk_reject_payload(self, risk: Dict[str, Any]) -> Dict[str, Any]:
        reason_code = str(risk.get("reason_code", "CONTENT_POLICY_VIOLATION")).strip()
        return {
            "error": CONTENT_POLICY_BLOCK_MESSAGE,
            "code": "content_policy_violation",
            "risk": {**risk, "reason_code": reason_code},
        }

    def is_risk_infra_failure(self, risk: Dict[str, Any]) -> bool:
        reason_code = str(risk.get("reason_code", "")).strip().upper()
        return reason_code in {
            "RISK_MODEL_AUTH_FAILED",
            "RISK_MODEL_CONFIG_INVALID",
            "RISK_MODEL_UNAVAILABLE",
            "RISK_FRAME_EXTRACTION_FAILED",
            "RISK_GATE_INTERNAL_ERROR",
        }

    def build_upload_risk_failure_response(self, risk: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        reason_code = str(risk.get("reason_code", "")).strip().upper()
        provider_error = str(risk.get("provider_error", "")).strip()
        request_id = _extract_request_id(provider_error)
        request_id_text = f"（请求 ID：{request_id}）" if request_id else ""
        if reason_code == "RISK_MODEL_AUTH_FAILED":
            auth_error = provider_error
            if not auth_error or "HTTP 401" in auth_error.upper():
                auth_error = (
                    "模型鉴权失败：API Key 无效、已过期，或与当前平台/Base URL 不匹配。"
                    f"{request_id_text}"
                )
            return (
                {
                    "error": auth_error,
                    "code": "risk_model_auth_failed",
                },
                401,
            )
        if reason_code == "RISK_MODEL_CONFIG_INVALID":
            config_error = provider_error
            has_specific_hint = (
                "模型连接失败：" in config_error
                or "模型鉴权失败：" in config_error
                or "模型服务请求超时" in config_error
                or "请求过于频繁" in config_error
            )
            if not has_specific_hint:
                config_error = (
                    "上传前模型配置校验失败：请检查模型接口 Base URL 与模型名称是否匹配当前平台，"
                    "并确认模型支持图片理解（风控检测依赖图片输入）。"
                    f"{request_id_text}"
                )
            return (
                {
                    "error": config_error,
                    "code": "risk_model_config_invalid",
                },
                400,
            )
        return self.upload_risk_unavailable_payload(), 503


upload_risk_service = UploadRiskService()


def _resolve_upload_risk_api_key() -> str:
    return upload_risk_service.resolve_upload_risk_api_key()


def _upload_risk_unavailable_message() -> str:
    return upload_risk_service.upload_risk_unavailable_message()


def _upload_risk_unavailable_payload() -> Dict[str, Any]:
    return upload_risk_service.upload_risk_unavailable_payload()


def _build_risk_agent_for_upload(
    api_key: str = "", model_name: str = "", model_base_url: str = ""
) -> VideoAnalyzerAgent:
    return upload_risk_service.build_risk_agent_for_upload(
        api_key=api_key,
        model_name=model_name,
        model_base_url=model_base_url,
    )


def _moderate_staged_upload(
    staged_video_path: Path,
    risk_agent: VideoAnalyzerAgent,
    file_fingerprint: str = "",
) -> Dict[str, Any]:
    return upload_risk_service.moderate_staged_upload(
        staged_video_path,
        risk_agent,
        file_fingerprint=file_fingerprint,
    )


def _risk_reject_payload(risk: Dict[str, Any]) -> Dict[str, Any]:
    return upload_risk_service.risk_reject_payload(risk)


def _is_risk_infra_failure(risk: Dict[str, Any]) -> bool:
    return upload_risk_service.is_risk_infra_failure(risk)


def _build_upload_risk_failure_response(risk: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    return upload_risk_service.build_upload_risk_failure_response(risk)


def _compute_video_fingerprint_safely(video_path: Path, source: str) -> str:
    try:
        return _compute_file_sha256(video_path)
    except OSError as exc:
        logger.warning("计算视频指纹失败（%s），将回退到非缓存路径: %s", source, exc)
        return ""


def _check_upload_blacklist_precheck(
    staged_video_path: Path,
    *,
    source: str,
    file_fingerprint: str = "",
) -> Tuple[Dict[str, Any] | None, str]:
    fingerprint = file_fingerprint or _compute_video_fingerprint_safely(staged_video_path, source)
    if fingerprint:
        blacklist_risk = _match_blacklisted_video_fingerprint_by_hash(fingerprint, source)
    else:
        blacklist_risk = _match_blacklisted_video_fingerprint(staged_video_path, source)
    if blacklist_risk is not None and fingerprint and not str(
        blacklist_risk.get("hash_sha256", "")
    ).strip():
        blacklist_risk["hash_sha256"] = fingerprint
    return blacklist_risk, fingerprint


def _run_upload_pre_risk_check(
    staged_video_path: Path,
    risk_agent: VideoAnalyzerAgent,
    *,
    source: str,
    file_fingerprint: str = "",
    skip_blacklist: bool = False,
) -> Tuple[Dict[str, Any], str, str]:
    fingerprint = file_fingerprint or _compute_video_fingerprint_safely(staged_video_path, source)
    if not skip_blacklist:
        blacklist_risk, fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staged_video_path,
            source=source,
            file_fingerprint=fingerprint,
        )
        if blacklist_risk is not None:
            return blacklist_risk, fingerprint, "blacklist"

    cache_model_key = _build_upload_risk_model_cache_key_from_agent(risk_agent)
    if fingerprint and cache_model_key:
        cached_risk = _get_cached_upload_risk_result(fingerprint, cache_model_key)
        if cached_risk is not None:
            logger.info(
                "上传前风控缓存命中: source=%s, sha256_prefix=%s",
                source,
                fingerprint[:12],
            )
            cached_risk["cache_hit"] = True
            cached_risk["cache_source"] = "upload_risk_precheck"
            if not str(cached_risk.get("hash_sha256", "")).strip():
                cached_risk["hash_sha256"] = fingerprint
            return cached_risk, fingerprint, "cache"

    risk = _moderate_staged_upload(
        staged_video_path,
        risk_agent,
        file_fingerprint=fingerprint,
    )
    if fingerprint and not str(risk.get("hash_sha256", "")).strip():
        risk["hash_sha256"] = fingerprint
    if (
        fingerprint
        and cache_model_key
        and not _is_risk_infra_failure(risk)
        and not _should_block_by_risk(str(risk.get("decision", "")))
    ):
        _set_cached_upload_risk_result(fingerprint, cache_model_key, risk)
        logger.info(
            "上传前风控缓存写入: source=%s, sha256_prefix=%s",
            source,
            fingerprint[:12],
        )
    return risk, fingerprint, "model"


def _normalize_processing_options(data: Dict[str, Any]) -> Tuple[str, bool, bool, int, float]:
    whisper_model = str(data.get("whisper_model", "base")).strip().lower() or "base"
    if whisper_model not in ALLOWED_WHISPER_MODELS:
        whisper_model = "base"

    use_video = _as_bool(data.get("use_video", False))
    web_search = _as_bool(data.get("web_search", False))
    max_vision = _safe_int(data.get("max_vision", 10), 10, 0, MAX_VISION_CALLS)
    fps = _safe_float(data.get("fps", 1.0), 1.0, FPS_MIN, FPS_MAX)
    return whisper_model, use_video, web_search, max_vision, fps


def _normalize_model_options(data: Dict[str, Any]) -> Tuple[str, str]:
    model_name = str(data.get("model_name", "")).strip() or DEFAULT_MODEL_NAME
    model_base_url = str(data.get("model_base_url", "")).strip() or DEFAULT_MODEL_BASE_URL

    if len(model_name) > 200:
        model_name = model_name[:200]
    if len(model_base_url) > 300:
        model_base_url = model_base_url[:300]

    return model_name, model_base_url


def _normalize_upload_model_options(
    data: Dict[str, Any],
    require_api_key: bool = False,
    require_model_name: bool = False,
) -> Tuple[str, str, str]:
    api_key = str(data.get("api_key", "")).strip()
    model_name = str(data.get("model_name", "")).strip()
    model_base_url = str(data.get("model_base_url", "")).strip()

    if len(api_key) > 500:
        api_key = api_key[:500]
    if len(model_name) > 200:
        model_name = model_name[:200]
    if len(model_base_url) > 300:
        model_base_url = model_base_url[:300]

    if require_api_key and not api_key:
        raise ValueError("请输入 API Key")
    if require_model_name and not model_name:
        raise ValueError("请填写模型名称")

    if not model_name:
        model_name = str(os.getenv("RISK_MODEL_NAME", "")).strip() or DEFAULT_MODEL_NAME
    if not model_base_url:
        model_base_url = (
            str(os.getenv("RISK_MODEL_BASE_URL", "")).strip() or DEFAULT_MODEL_BASE_URL
        )
    return api_key, model_name, model_base_url


class VideoProcessingService:
    def process_video(
        self,
        video_path: Path,
        api_key: str,
        whisper_model: str,
        model_name: str,
        model_base_url: str,
        use_video: bool,
        web_search: bool,
        max_vision: int,
        fps: float = 1.0,
        history_owner_id: str = "",
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> Tuple[List[Dict[str, Any]], str, str, str, bool]:
        def report(stage: str, message: str) -> None:
            if progress_callback:
                progress_callback(stage, message)

        report("prepare", "\u6b63\u5728\u51c6\u5907\u5206\u6790\u4efb\u52a1...")
        output_dir = _create_unique_output_dir(video_path)

        agent = VideoAnalyzerAgent(
            api_key if api_key else None,
            whisper_model,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        report("moderation", "正在执行黑名单指纹比对...")
        video_fingerprint = _compute_video_fingerprint_safely(video_path, "analyze")
        if video_fingerprint:
            blacklist_risk = _match_blacklisted_video_fingerprint_by_hash(
                video_fingerprint, source="analyze"
            )
        else:
            blacklist_risk = _match_blacklisted_video_fingerprint(video_path, source="analyze")
        if blacklist_risk is not None:
            quarantine_path = _quarantine_upload_file(video_path, str(blacklist_risk.get("reason_code", "")))
            if quarantine_path is not None:
                blacklist_risk["quarantine_path"] = str(quarantine_path)
            shutil.rmtree(output_dir, ignore_errors=True)
            raise ContentPolicyBlockedError(
                "视频命中黑名单指纹（SHA-256 完全一致），已拒绝处理。",
                blacklist_risk,
            )

        report("moderation", "正在执行内容风控检测...")
        risk_cache_model_key = _build_upload_risk_model_cache_key_from_agent(agent)
        risk_frame_dir = output_dir / ".risk_frames"
        cached_risk = (
            _get_cached_upload_risk_result(video_fingerprint, risk_cache_model_key)
            if video_fingerprint and risk_cache_model_key
            else None
        )
        if cached_risk is not None:
            logger.info("分析前风控缓存命中: sha256_prefix=%s", video_fingerprint[:12])
            cached_risk["cache_hit"] = True
            cached_risk["cache_source"] = "analyze_risk_precheck"
            if not str(cached_risk.get("hash_sha256", "")).strip():
                cached_risk["hash_sha256"] = video_fingerprint
            risk = cached_risk
        else:
            risk, risk_frame_dir = _run_video_risk_gate(
                agent,
                video_path,
                output_dir,
                subtitle_cache_identity=video_fingerprint,
            )
            if video_fingerprint and not str(risk.get("hash_sha256", "")).strip():
                risk["hash_sha256"] = video_fingerprint
            if (
                video_fingerprint
                and risk_cache_model_key
                and not _is_risk_infra_failure(risk)
                and not _should_block_by_risk(str(risk.get("decision", "")))
            ):
                _set_cached_upload_risk_result(video_fingerprint, risk_cache_model_key, risk)

        if _is_risk_infra_failure(risk):
            if risk_frame_dir.exists():
                shutil.rmtree(risk_frame_dir, ignore_errors=True)
            shutil.rmtree(output_dir, ignore_errors=True)
            raise RuntimeError(
                str(risk.get("provider_error") or risk.get("reason") or "风控服务不可用")
            )
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    video_fingerprint, risk, source="analyze_risk_block"
                )
                if video_fingerprint
                else _register_blocked_video_fingerprint(
                    video_path, risk, source="analyze_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            quarantine_path = _quarantine_upload_file(video_path, str(risk.get("reason_code", "")))
            if quarantine_path is not None:
                risk["quarantine_path"] = str(quarantine_path)
            shutil.rmtree(output_dir, ignore_errors=True)
            raise ContentPolicyBlockedError(
                f"视频触发风控策略（{risk.get('reason_code', 'CONTENT_POLICY_VIOLATION')}）：{risk.get('reason', '内容敏感')}",
                risk,
            )

        if risk_frame_dir.exists():
            shutil.rmtree(risk_frame_dir, ignore_errors=True)

        video_dest = output_dir / video_path.name
        if not video_dest.exists():
            shutil.copy2(video_path, video_dest)

        srt_path = None

        if not use_video:
            report("subtitle", "\u6b63\u5728\u751f\u6210\u5b57\u5e55...")
            srt_path = agent.generate_subtitles(
                str(video_path),
                str(output_dir),
                cache_identity=video_fingerprint or None,
            )
            report("analysis", "\u6b63\u5728\u5206\u6790\u5b57\u5e55\u5185\u5bb9...")
            steps = _run_async(agent.analyze_subtitles(srt_path))
        else:
            report("subtitle", "\u6b63\u5728\u5c1d\u8bd5\u751f\u6210\u5b57\u5e55...")
            try:
                srt_path = agent.generate_subtitles(
                    str(video_path),
                    str(output_dir),
                    cache_identity=video_fingerprint or None,
                )
            except Exception as exc:
                logger.warning("Whisper 字幕生成失败，继续视频分析模式: %s", exc)
                srt_path = None
            report("analysis", "\u6b63\u5728\u5206\u6790\u89c6\u9891\u753b\u9762...")
            steps = _run_async(agent.analyze_video(str(video_path), fps))

        if not steps:
            report("analysis", "\u672a\u8bc6\u522b\u5230\u6709\u6548\u6b65\u9aa4")
            return [], "", str(output_dir), str(output_dir / "operation_guide.pdf"), False

        image_dir = output_dir / "images"
        image_dir.mkdir(exist_ok=True)
        report("screenshots", "\u6b63\u5728\u751f\u6210\u5173\u952e\u622a\u56fe...")
        agent.generate_screenshots_from_steps(str(video_path), steps, str(image_dir))

        if max_vision > 0 and not use_video and srt_path:
            report("vision", "\u6b63\u5728\u8fdb\u884c\u89c6\u89c9\u589e\u5f3a...")
            steps = _run_async(
                agent.enhance_steps_with_vision(
                    steps, str(image_dir), srt_path=srt_path, max_calls=max_vision
                )
            )

        output_md = output_dir / "operation_guide.md"
        report("document", "\u6b63\u5728\u751f\u6210\u603b\u7ed3\u6587\u6863...")
        _run_async(
            agent.generate_step_document(
                steps=steps,
                output_path=str(output_md),
                srt_path=srt_path if srt_path else None,
                image_dir="images",
                web_search=web_search,
            )
        )

        output_pdf = output_dir / "operation_guide.pdf"
        report("pdf", "\u6b63\u5728\u751f\u6210 PDF...")
        agent.generate_pdf(str(output_md), str(output_pdf))
        agent.save_results(steps, str(output_dir / "steps.json"))
        report("done", "\u5f53\u524d\u89c6\u9891\u5206\u6790\u5b8c\u6210")

        has_steps = len(steps) > 0
        if has_steps:
            record = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "video_name": video_path.name,
                "output_dir": str(output_dir),
                "steps_count": len(steps),
                "mode": "video" if use_video else "subtitle",
                "whisper_model": whisper_model,
                "model_name": model_name,
                "model_base_url": model_base_url,
                "use_video": use_video,
                "web_search": web_search,
                "max_vision": max_vision,
                "pdf_path": str(output_pdf),
                "risk_decision": str(risk.get("decision", "allow")),
                "risk_level": str(risk.get("risk_level", "low")),
                "risk_reason_code": str(risk.get("reason_code", "SAFE_CONTENT")),
            }
            save_history(record, history_owner_id)

        with open(output_md, "r", encoding="utf-8") as f:
            md_content = f.read()

        return steps, md_content, str(output_dir), str(output_pdf), has_steps


video_processing_service = VideoProcessingService()


class BackendServiceContainer:
    def __init__(self):
        self.risk_fallback_env = risk_fallback_env_service
        self.progress = progress_state_service
        self.risk_blocklist = risk_blocklist_service
        self.risk_result_cache = risk_result_cache_service
        self.history = history_service
        self.upload_session = upload_session_service
        self.upload_risk = upload_risk_service
        self.video_processing = video_processing_service


backend_services = BackendServiceContainer()


def process_video(
    video_path: Path,
    api_key: str,
    whisper_model: str,
    model_name: str,
    model_base_url: str,
    use_video: bool,
    web_search: bool,
    max_vision: int,
    fps: float = 1.0,
    history_owner_id: str = "",
    progress_callback: Callable[[str, str], None] | None = None,
) -> Tuple[List[Dict[str, Any]], str, str, str, bool]:
    return video_processing_service.process_video(
        video_path=video_path,
        api_key=api_key,
        whisper_model=whisper_model,
        model_name=model_name,
        model_base_url=model_base_url,
        use_video=use_video,
        web_search=web_search,
        max_vision=max_vision,
        fps=fps,
        history_owner_id=history_owner_id,
        progress_callback=progress_callback,
    )


@app.route("/")
def index():
    return jsonify(
        {
            "service": "video-to-doc-api",
            "status": "ok",
            "frontend": "Run web-react independently (e.g. npm run dev in /web-react).",
        }
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "不支持的文件格式"}), 400

    upload_api_key, upload_model_name, upload_model_base_url = _normalize_upload_model_options(
        {
            "api_key": request.form.get("api_key", ""),
            "model_name": request.form.get("model_name", ""),
            "model_base_url": request.form.get("model_base_url", ""),
        }
    )

    staged_path = _build_upload_staging_path(file.filename)
    try:
        file.save(str(staged_path))
        blacklist_risk, file_fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staged_path,
            source="upload_single",
        )
        if blacklist_risk is not None:
            _safe_remove_file(staged_path)
            return jsonify(_risk_reject_payload(blacklist_risk)), 403

        risk_agent = _build_risk_agent_for_upload(
            upload_api_key, upload_model_name, upload_model_base_url
        )
        risk, file_fingerprint, _ = _run_upload_pre_risk_check(
            staged_video_path=staged_path,
            risk_agent=risk_agent,
            source="upload_single",
            file_fingerprint=file_fingerprint,
            skip_blacklist=True,
        )
        if _is_risk_infra_failure(risk):
            _safe_remove_file(staged_path)
            logger.warning("上传风控服务异常（single upload）: %s", risk)
            payload, status_code = _build_upload_risk_failure_response(risk)
            return jsonify(payload), status_code
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    file_fingerprint, risk, source="upload_single_risk_block"
                )
                if file_fingerprint
                else _register_blocked_video_fingerprint(
                    staged_path, risk, source="upload_single_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            _safe_remove_file(staged_path)
            return jsonify(_risk_reject_payload(risk)), 403

        save_path = _build_unique_upload_path(file.filename)
        shutil.move(str(staged_path), str(save_path))
        return jsonify({"filename": save_path.name, "filepath": str(save_path)})
    except ValueError as exc:
        _safe_remove_file(staged_path)
        logger.warning("上传风控不可用（single upload）: %s", exc)
        return jsonify(_upload_risk_unavailable_payload()), 503
    except Exception as exc:
        _safe_remove_file(staged_path)
        return jsonify({"error": f"上传失败: {str(exc)}"}), 500


@app.route("/upload_chunk_init", methods=["POST"])
def upload_chunk_init():
    data = _json_payload()
    filename = str(data.get("filename", "")).strip()
    if not filename:
        return jsonify({"error": "文件名不能为空"}), 400
    if not allowed_file(filename):
        return jsonify({"error": "不支持的文件格式"}), 400

    total_size = _safe_int(data.get("total_size"), 0, 1)
    if total_size <= 0:
        return jsonify({"error": "文件大小无效"}), 400

    requested_chunk_size = _safe_int(
        data.get("chunk_size", DEFAULT_UPLOAD_CHUNK_SIZE),
        DEFAULT_UPLOAD_CHUNK_SIZE,
        256 * 1024,
        MAX_UPLOAD_CHUNK_SIZE,
    )
    file_key = str(data.get("file_key", "")).strip()
    try:
        upload_api_key, upload_model_name, upload_model_base_url = (
            _normalize_upload_model_options(
                data,
                require_api_key=True,
                require_model_name=True,
            )
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        requested_upload_id = _normalize_upload_id(data.get("upload_id", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with upload_session_lock:
        session: Dict[str, Any] | None = None
        upload_id = requested_upload_id

        if upload_id:
            session = _load_upload_session(upload_id)
            if session is not None:
                same_name = str(session.get("filename", "")) == filename
                same_size = _safe_int(session.get("total_size"), -1) == total_size
                same_key = not file_key or str(session.get("file_key", "")) == file_key
                same_model = (
                    str(session.get("risk_api_key", "")).strip() == upload_api_key
                    and str(session.get("risk_model_name", "")).strip()
                    == upload_model_name
                    and str(session.get("risk_model_base_url", "")).strip()
                    == upload_model_base_url
                )
                if not (same_name and same_size and same_key and same_model):
                    session = None
                else:
                    total_chunks = _safe_int(session.get("total_chunks"), 1, 1)
                    received_chunks = _normalize_received_chunks(
                        session.get("received_chunks", []), total_chunks
                    )
                    session["received_chunks"] = received_chunks
                    if _get_chunk_storage_mode(session) == "memory":
                        if upload_id not in upload_memory_buffers and received_chunks:
                            # Memory-mode sessions cannot recover buffered chunks after process restart.
                            _delete_upload_session(upload_id)
                            session = None
                        elif upload_id not in upload_memory_buffers:
                            if _reserve_upload_memory(upload_id, total_size):
                                session["storage_mode"] = "memory"
                            else:
                                session["storage_mode"] = "disk"

        if session is None:
            upload_id = uuid4().hex
            total_chunks = max(1, (total_size + requested_chunk_size - 1) // requested_chunk_size)
            storage_mode = "disk"
            if total_size <= UPLOAD_IN_MEMORY_MAX_FILE_SIZE and _reserve_upload_memory(
                upload_id, total_size
            ):
                storage_mode = "memory"
            session = {
                "upload_id": upload_id,
                "filename": filename,
                "file_key": file_key,
                "total_size": total_size,
                "chunk_size": requested_chunk_size,
                "total_chunks": total_chunks,
                "received_chunks": [],
                "storage_mode": storage_mode,
                "risk_api_key": upload_api_key,
                "risk_model_name": upload_model_name,
                "risk_model_base_url": upload_model_base_url,
                "created_at": now_text,
                "updated_at": now_text,
            }
            try:
                _save_upload_session(upload_id, session)
            except Exception:
                if storage_mode == "memory":
                    _release_upload_memory(upload_id)
                raise
        else:
            total_chunks = _safe_int(session.get("total_chunks"), 1, 1)
            session["received_chunks"] = _normalize_received_chunks(
                session.get("received_chunks", []), total_chunks
            )
            if _get_chunk_storage_mode(session) == "memory":
                if not _reserve_upload_memory(upload_id, total_size):
                    session["storage_mode"] = "disk"
            else:
                _release_upload_memory(upload_id)
            session["risk_api_key"] = upload_api_key
            session["risk_model_name"] = upload_model_name
            session["risk_model_base_url"] = upload_model_base_url
            session["updated_at"] = now_text
            _save_upload_session(upload_id, session)

    return jsonify(
        {
            "success": True,
            "upload_id": upload_id,
            "chunk_size": _safe_int(session.get("chunk_size"), DEFAULT_UPLOAD_CHUNK_SIZE, 1),
            "total_chunks": _safe_int(session.get("total_chunks"), 1, 1),
            "received_chunks": session.get("received_chunks", []),
            "storage_mode": _get_chunk_storage_mode(session),
        }
    )


@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    if "chunk" not in request.files:
        return jsonify({"error": "缺少分片文件"}), 400

    try:
        upload_id = _normalize_upload_id(request.form.get("upload_id", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not upload_id:
        return jsonify({"error": "upload_id 不能为空"}), 400

    chunk_index = _safe_int(request.form.get("chunk_index"), -1)
    if chunk_index < 0:
        return jsonify({"error": "chunk_index 无效"}), 400

    chunk_file = request.files["chunk"]
    chunk_data = chunk_file.read() or b""

    with upload_session_lock:
        session = _load_upload_session(upload_id)
        if session is None:
            return jsonify({"error": "上传会话不存在，请重新开始上传"}), 404

        total_chunks = _safe_int(session.get("total_chunks"), 0, 1)
        chunk_size = _safe_int(
            session.get("chunk_size"), DEFAULT_UPLOAD_CHUNK_SIZE, 1, MAX_UPLOAD_CHUNK_SIZE
        )
        total_size = _safe_int(session.get("total_size"), 0, 1)

        if chunk_index >= total_chunks:
            return jsonify({"error": "chunk_index 超出范围"}), 400

        offset = chunk_index * chunk_size
        if offset >= total_size:
            return jsonify({"error": "分片偏移量无效"}), 400

        expected_max_size = min(chunk_size, total_size - offset)
        if len(chunk_data) == 0 and expected_max_size > 0:
            return jsonify({"error": "分片内容为空"}), 400
        if len(chunk_data) > expected_max_size:
            return jsonify({"error": "分片大小超出限制"}), 400

        storage_mode = _get_chunk_storage_mode(session)
        if storage_mode == "memory":
            chunk_buffer = upload_memory_buffers.get(upload_id)
            existing_received = _normalize_received_chunks(
                session.get("received_chunks", []), total_chunks
            )
            if chunk_buffer is None and existing_received:
                _delete_upload_session(upload_id)
                return jsonify({"error": "上传会话已过期，请重新开始上传"}), 409
            if chunk_buffer is None:
                if not _reserve_upload_memory(upload_id, total_size):
                    return jsonify({"error": "上传繁忙，请稍后重试"}), 503
                session["storage_mode"] = "memory"
                chunk_buffer = upload_memory_buffers.setdefault(upload_id, {})
            chunk_buffer[chunk_index] = chunk_data
        else:
            temp_path = _upload_session_temp_path(upload_id)
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            if not temp_path.exists():
                with open(temp_path, "wb"):
                    pass

            with open(temp_path, "r+b") as f:
                f.seek(offset)
                f.write(chunk_data)

        received_chunks = set(
            _normalize_received_chunks(session.get("received_chunks", []), total_chunks)
        )
        received_chunks.add(chunk_index)
        session["received_chunks"] = sorted(received_chunks)
        session["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_upload_session(upload_id, session)

    return jsonify(
        {
            "success": True,
            "upload_id": upload_id,
            "uploaded_chunks": len(session["received_chunks"]),
            "total_chunks": total_chunks,
        }
    )


@app.route("/upload_chunk_finalize", methods=["POST"])
def upload_chunk_finalize():
    data = _json_payload()
    try:
        upload_id = _normalize_upload_id(data.get("upload_id", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not upload_id:
        return jsonify({"error": "upload_id 不能为空"}), 400

    filename = ""
    total_size = 0
    staging_path: Path | None = None
    risk_api_key = ""
    risk_model_name = ""
    risk_model_base_url = ""

    with upload_session_lock:
        session = _load_upload_session(upload_id)
        if session is None:
            return jsonify({"error": "上传会话不存在，请重新开始上传"}), 404

        filename = str(session.get("filename", "")).strip()
        if not filename or not allowed_file(filename):
            return jsonify({"error": "原始文件名无效"}), 400
        risk_api_key = str(session.get("risk_api_key", "")).strip()
        risk_model_name = str(session.get("risk_model_name", "")).strip()
        risk_model_base_url = str(session.get("risk_model_base_url", "")).strip()

        total_chunks = _safe_int(session.get("total_chunks"), 0, 1)
        total_size = _safe_int(session.get("total_size"), 0, 1)
        received_chunks = _normalize_received_chunks(session.get("received_chunks", []), total_chunks)
        if len(received_chunks) < total_chunks:
            received_set = set(received_chunks)
            missing_chunks = [i for i in range(total_chunks) if i not in received_set][:10]
            missing_text = ",".join(str(i) for i in missing_chunks)
            suffix = "..." if len(received_chunks) + len(missing_chunks) < total_chunks else ""
            return jsonify({"error": f"分片未上传完整，缺少分片: {missing_text}{suffix}"}), 400

        storage_mode = _get_chunk_storage_mode(session)
        staging_path = _build_upload_staging_path(filename)
        if storage_mode == "memory":
            chunk_buffer = upload_memory_buffers.get(upload_id)
            if chunk_buffer is None:
                _delete_upload_session(upload_id)
                return jsonify({"error": "上传会话已过期，请重新开始上传"}), 409

            all_missing = [i for i in range(total_chunks) if i not in chunk_buffer]
            missing_buffer = all_missing[:10]
            if missing_buffer:
                missing_text = ",".join(str(i) for i in missing_buffer)
                suffix = "..." if len(all_missing) > len(missing_buffer) else ""
                return jsonify({"error": f"分片缓存不完整，缺少分片: {missing_text}{suffix}"}), 400

            with open(staging_path, "wb") as f:
                for idx in range(total_chunks):
                    f.write(chunk_buffer.get(idx, b""))
                if f.tell() > total_size:
                    f.truncate(total_size)
        else:
            temp_path = _upload_session_temp_path(upload_id)
            if not temp_path.exists():
                return jsonify({"error": "临时文件不存在，请重新上传"}), 400

            if temp_path.stat().st_size < total_size:
                return jsonify({"error": "文件尚未完整上传，请继续上传缺失分片"}), 400

            if temp_path.stat().st_size > total_size:
                with open(temp_path, "r+b") as f:
                    f.truncate(total_size)

            shutil.move(str(temp_path), str(staging_path))
        _delete_upload_session(upload_id)

    if staging_path is None:
        return jsonify({"error": "上传文件状态异常"}), 500

    try:
        blacklist_risk, file_fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staging_path,
            source="upload_chunk_finalize",
        )
        if blacklist_risk is not None:
            _safe_remove_file(staging_path)
            return jsonify(_risk_reject_payload(blacklist_risk)), 403

        risk_agent = _build_risk_agent_for_upload(
            risk_api_key, risk_model_name, risk_model_base_url
        )
        risk, file_fingerprint, _ = _run_upload_pre_risk_check(
            staged_video_path=staging_path,
            risk_agent=risk_agent,
            source="upload_chunk_finalize",
            file_fingerprint=file_fingerprint,
            skip_blacklist=True,
        )
        if _is_risk_infra_failure(risk):
            _safe_remove_file(staging_path)
            logger.warning("上传风控服务异常（chunk finalize）: %s", risk)
            payload, status_code = _build_upload_risk_failure_response(risk)
            return jsonify(payload), status_code
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    file_fingerprint, risk, source="upload_chunk_finalize_risk_block"
                )
                if file_fingerprint
                else _register_blocked_video_fingerprint(
                    staging_path, risk, source="upload_chunk_finalize_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            _safe_remove_file(staging_path)
            return jsonify(_risk_reject_payload(risk)), 403

        save_path = _build_unique_upload_path(filename)
        shutil.move(str(staging_path), str(save_path))
        if save_path.stat().st_size > total_size:
            with open(save_path, "r+b") as f:
                f.truncate(total_size)
        return jsonify({"success": True, "filename": save_path.name, "filepath": str(save_path)})
    except ValueError as exc:
        _safe_remove_file(staging_path)
        logger.warning("上传风控不可用（chunk finalize）: %s", exc)
        return jsonify(_upload_risk_unavailable_payload()), 503
    except Exception as exc:
        _safe_remove_file(staging_path)
        return jsonify({"error": f"上传失败: {str(exc)}"}), 500


@app.route("/analyze", methods=["POST"])
def analyze():
    data = _json_payload()
    history_owner_id = _ensure_history_owner()
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        return jsonify({"error": "请输入 API Key"}), 400

    whisper_model, use_video, web_search, max_vision, fps = _normalize_processing_options(
        data
    )
    model_name, model_base_url = _normalize_model_options(data)

    try:
        video_path = _resolve_upload_filepath(data.get("filepath"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "文件不存在"}), 400

    try:
        _update_single_progress(
            status="processing",
            current_file=video_path.name,
            stage="prepare",
            message="\u4efb\u52a1\u5df2\u542f\u52a8\uff0c\u6b63\u5728\u521d\u59cb\u5316...",
        )

        def _single_progress_callback(stage: str, message: str) -> None:
            _update_single_progress(
                status="processing",
                current_file=video_path.name,
                stage=stage,
                message=message,
            )

        steps, md_content, output_dir, output_pdf, has_steps = process_video(
            video_path,
            api_key,
            whisper_model,
            model_name,
            model_base_url,
            use_video,
            web_search,
            max_vision,
            fps,
            history_owner_id=history_owner_id,
            progress_callback=_single_progress_callback,
        )
        if not has_steps:
            _update_single_progress(
                status="failed",
                stage="failed",
                message="\u672a\u80fd\u8bc6\u522b\u5230\u64cd\u4f5c\u6b65\u9aa4",
            )
            return jsonify({"error": "未能识别到操作步骤"}), 500

        _update_single_progress(
            status="completed",
            stage="done",
            message="\u89c6\u9891\u5206\u6790\u5df2\u5b8c\u6210",
        )
        return jsonify(
            {
                "success": True,
                "steps": steps,
                "markdown": md_content,
                "output_dir": output_dir,
                "pdf_path": output_pdf,
            }
        )
    except ContentPolicyBlockedError as exc:
        _update_single_progress(
            status="failed",
            stage="moderation",
            message=str(exc),
        )
        return (
            jsonify(
                {
                    "error": str(exc),
                    "code": "content_policy_violation",
                    "risk": exc.risk,
                }
            ),
            403,
        )
    except Exception as exc:
        error_message, status_code, normalized = _normalize_provider_error(
            exc, default_status=500
        )
        _update_single_progress(
            status="failed",
            stage="failed",
            message=error_message,
        )
        payload: Dict[str, Any] = {"error": error_message}
        if status_code >= 500 and not normalized:
            payload["trace"] = traceback.format_exc()
        return jsonify(payload), status_code


@app.route("/test_model", methods=["POST"])
def test_model():
    data = _json_payload()
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        return jsonify({"error": "请输入 API Key"}), 400

    model_name = str(data.get("model_name", "")).strip()
    model_base_url = str(data.get("model_base_url", "")).strip()
    if len(model_name) > 200:
        model_name = model_name[:200]
    if len(model_base_url) > 300:
        model_base_url = model_base_url[:300]

    if not model_name:
        return jsonify({"error": "请填写模型名称"}), 400
    if not model_base_url:
        return jsonify({"error": "请填写模型接口 Base URL"}), 400

    try:
        agent = VideoAnalyzerAgent(
            api_key=api_key,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        result = _run_async(agent.test_model_connection())
        return jsonify(
            {
                "success": True,
                "message": "模型连接测试成功",
                "model_name": model_name,
                "model_base_url": model_base_url,
                "reply": str(result.get("reply", "") or ""),
            }
        )
    except Exception as exc:
        error_message, status_code, _ = _normalize_provider_error(exc, default_status=500)
        return jsonify({"error": f"模型连接测试失败：{error_message}"}), status_code


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename, as_attachment=True)


@app.route("/download_zip/<output_dir>")
def download_zip(output_dir):
    try:
        output_path = _resolve_output_dir(output_dir, must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "文件不存在"}), 404

    md_file = output_path / "operation_guide.md"
    pdf_file = output_path / "operation_guide.pdf"
    images_dir = output_path / "images"

    if not md_file.exists():
        return jsonify({"error": "文件不存在"}), 404

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(md_file, "operation_guide.md")
        if pdf_file.exists():
            zf.write(pdf_file, "operation_guide.pdf")
        if images_dir.exists():
            for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                for img_file in images_dir.glob(pattern):
                    zf.write(img_file, f"images/{img_file.name}")

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{output_path.name}.zip",
    )


@app.route("/output/<path:filename>")
def serve_output_file(filename):
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename)


@app.route("/regenerate", methods=["POST"])
def regenerate_document():
    data = _json_payload()
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        return jsonify({"error": "请输入 API Key"}), 400

    steps = data.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return jsonify({"error": "没有步骤数据"}), 400

    try:
        output_dir = _resolve_output_dir(data.get("output_dir"), must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "输出目录不存在"}), 400

    web_search = _as_bool(data.get("web_search", False))
    model_name, model_base_url = _normalize_model_options(data)

    try:
        agent = VideoAnalyzerAgent(
            api_key,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        output_path = output_dir / "operation_guide.md"
        _run_async(
            agent.generate_step_document(
                steps=steps,
                output_path=str(output_path),
                srt_path=None,
                image_dir="images",
                web_search=web_search,
                respect_step_content=True,
            )
        )

        output_pdf = output_dir / "operation_guide.pdf"
        agent.generate_pdf(str(output_path), str(output_pdf))
        agent.save_results(steps, str(output_dir / "steps.json"))

        with open(output_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        return jsonify(
            {
                "success": True,
                "steps": steps,
                "markdown": md_content,
                "output_dir": str(output_dir),
                "pdf_path": str(output_pdf),
            }
        )
    except Exception as exc:
        error_message, status_code, normalized = _normalize_provider_error(
            exc, default_status=500
        )
        payload: Dict[str, Any] = {"error": error_message}
        if status_code >= 500 and not normalized:
            payload["trace"] = traceback.format_exc()
        return jsonify(payload), status_code


@app.route("/cleanup/<filename>")
def cleanup(filename):
    try:
        safe_name = secure_filename(filename)
        if not safe_name:
            return jsonify({"error": "文件名无效"}), 400

        upload_file_path = UPLOAD_ROOT / safe_name
        if upload_file_path.exists():
            upload_file_path.unlink()

        # 兼容旧目录命名: outputs/<stem>
        legacy_output_dir = OUTPUT_ROOT / Path(safe_name).stem
        if legacy_output_dir.exists() and legacy_output_dir.is_dir():
            shutil.rmtree(legacy_output_dir)

        # 新目录命名: outputs/<stem>_<timestamp>
        stem_prefix = secure_filename(Path(safe_name).stem)
        if stem_prefix:
            for output_dir in OUTPUT_ROOT.glob(f"{stem_prefix}_*"):
                if output_dir.is_dir():
                    shutil.rmtree(output_dir)

        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/history", methods=["GET"])
def get_history():
    owner_id = _ensure_history_owner()
    history = [_strip_owner_field(item) for item in load_history(owner_id)]
    return jsonify({"history": history})


@app.route("/history/<record_id>", methods=["GET"])
def get_history_record(record_id):
    owner_id = _ensure_history_owner()
    history = load_history(owner_id)
    for item in history:
        if item.get("id") != record_id:
            continue

        record = _strip_owner_field(item)
        output_dir_value = record.get("output_dir")
        if output_dir_value:
            try:
                output_dir = _resolve_output_dir(output_dir_value, must_exist=True)
            except (ValueError, FileNotFoundError):
                output_dir = None

            if output_dir:
                steps_path = output_dir / "steps.json"
                md_path = output_dir / "operation_guide.md"

                if steps_path.exists():
                    with open(steps_path, "r", encoding="utf-8") as f:
                        record["steps"] = json.load(f)
                if md_path.exists():
                    with open(md_path, "r", encoding="utf-8") as f:
                        record["markdown"] = f.read()

        return jsonify({"record": record})

    return jsonify({"error": "记录不存在"}), 404


@app.route("/history/<record_id>", methods=["DELETE"])
def delete_history(record_id):
    owner_id = _ensure_history_owner()
    try:
        delete_history_record(record_id, owner_id)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/upload_batch", methods=["POST"])
def upload_batch_files():
    if "files" not in request.files:
        return jsonify({"error": "没有文件"}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "没有选择文件"}), 400

    upload_api_key, upload_model_name, upload_model_base_url = _normalize_upload_model_options(
        {
            "api_key": request.form.get("api_key", ""),
            "model_name": request.form.get("model_name", ""),
            "model_base_url": request.form.get("model_base_url", ""),
        }
    )

    uploaded = []
    errors = []
    try:
        risk_agent = _build_risk_agent_for_upload(
            upload_api_key, upload_model_name, upload_model_base_url
        )
    except ValueError as exc:
        logger.warning("上传风控不可用（batch upload）: %s", exc)
        return jsonify(_upload_risk_unavailable_payload()), 503

    for file in files:
        if not file or file.filename == "":
            continue
        if not allowed_file(file.filename):
            errors.append(f"{file.filename}: 不支持的格式")
            continue

        staged_path = _build_upload_staging_path(file.filename)
        try:
            file.save(str(staged_path))
            risk, file_fingerprint, risk_source = _run_upload_pre_risk_check(
                staged_video_path=staged_path,
                risk_agent=risk_agent,
                source="upload_batch",
            )
            if risk_source == "blacklist":
                _safe_remove_file(staged_path)
                errors.append(f"{file.filename}: 命中黑名单指纹拦截（完全一致视频）")
                continue

            if _is_risk_infra_failure(risk):
                _safe_remove_file(staged_path)
                payload, _ = _build_upload_risk_failure_response(risk)
                errors.append(f"{file.filename}: {str(payload.get('error', '上传风控服务不可用'))}")
                continue
            if _should_block_by_risk(str(risk.get("decision", ""))):
                blocked_hash = (
                    _register_blocked_video_fingerprint_by_hash(
                        file_fingerprint, risk, source="upload_batch_risk_block"
                    )
                    if file_fingerprint
                    else _register_blocked_video_fingerprint(
                        staged_path, risk, source="upload_batch_risk_block"
                    )
                )
                if blocked_hash:
                    risk["hash_sha256"] = blocked_hash
                _safe_remove_file(staged_path)
                errors.append(f"{file.filename}: {CONTENT_POLICY_BLOCK_MESSAGE}")
                continue

            save_path = _build_unique_upload_path(file.filename)
            shutil.move(str(staged_path), str(save_path))
            uploaded.append({"filename": save_path.name, "filepath": str(save_path)})
        except Exception as exc:
            _safe_remove_file(staged_path)
            errors.append(f"{file.filename}: {str(exc)}")

    return jsonify({"uploaded": uploaded, "errors": errors, "total": len(files)})


@app.route("/batch_progress", methods=["GET"])
def get_batch_progress():
    return jsonify(progress_state_service.get_batch_snapshot())


@app.route("/single_progress", methods=["GET"])
def get_single_progress():
    return jsonify(progress_state_service.get_single_snapshot())


@app.route("/analyze_batch", methods=["POST"])
def analyze_batch():
    data = _json_payload()
    history_owner_id = _ensure_history_owner()
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        return jsonify({"error": "请输入 API Key"}), 400

    raw_filepaths = data.get("filepaths", [])
    if not isinstance(raw_filepaths, list) or not raw_filepaths:
        return jsonify({"error": "没有视频文件"}), 400

    whisper_model, use_video, web_search, max_vision, fps = _normalize_processing_options(
        data
    )
    model_name, model_base_url = _normalize_model_options(data)

    filepaths: List[Path] = []
    for raw_path in raw_filepaths:
        try:
            filepaths.append(_resolve_upload_filepath(raw_path))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except FileNotFoundError:
            return jsonify({"error": f"文件不存在: {raw_path}"}), 400

    _update_batch_progress(
        total=len(filepaths),
        current=0,
        status="processing",
        current_file="",
        stage="prepare",
        message="\u6279\u91cf\u4efb\u52a1\u5df2\u542f\u52a8\uff0c\u6b63\u5728\u7b49\u5f85\u5904\u7406...",
    )

    results = []
    try:
        for idx, filepath in enumerate(filepaths, start=1):
            _update_batch_progress(
                current=idx,
                current_file=filepath.name,
                stage="prepare",
                message=f"\u6b63\u5728\u51c6\u5907\u5904\u7406: {filepath.name}",
            )

            def _batch_progress_callback(stage: str, message: str, *, _idx=idx, _name=filepath.name):
                _update_batch_progress(
                    current=_idx,
                    current_file=_name,
                    stage=stage,
                    message=message,
                )

            try:
                steps, md_content, output_dir, output_pdf, has_steps = process_video(
                    filepath,
                    api_key,
                    whisper_model,
                    model_name,
                    model_base_url,
                    use_video,
                    web_search,
                    max_vision,
                    fps,
                    history_owner_id=history_owner_id,
                    progress_callback=_batch_progress_callback,
                )

                if not has_steps:
                    _update_batch_progress(
                        current=idx,
                        current_file=filepath.name,
                        stage="failed",
                        message="\u672a\u80fd\u8bc6\u522b\u5230\u64cd\u4f5c\u6b65\u9aa4",
                    )
                    results.append(
                        {
                            "index": idx,
                            "filename": filepath.name,
                            "success": False,
                            "error": "未识别到操作步骤",
                        }
                    )
                    continue

                results.append(
                    {
                        "index": idx,
                        "filename": filepath.name,
                        "success": True,
                        "steps_count": len(steps) if steps else 0,
                        "output_dir": output_dir,
                        "pdf_path": output_pdf,
                        "markdown": md_content,
                        "steps": steps,
                    }
                )
                _update_batch_progress(
                    current=idx,
                    current_file=filepath.name,
                    stage="done",
                    message=f"{filepath.name} \u5206\u6790\u5b8c\u6210",
                )
            except ContentPolicyBlockedError as exc:
                _update_batch_progress(
                    current=idx,
                    current_file=filepath.name,
                    stage="moderation",
                    message=str(exc),
                )
                results.append(
                    {
                        "index": idx,
                        "filename": filepath.name,
                        "success": False,
                        "error": str(exc),
                        "code": "content_policy_violation",
                        "risk": exc.risk,
                    }
                )
            except Exception as exc:
                error_msg, _, _ = _normalize_provider_error(exc, default_status=500)
                _update_batch_progress(
                    current=idx,
                    current_file=filepath.name,
                    stage="failed",
                    message=error_msg,
                )
                results.append(
                    {
                        "index": idx,
                        "filename": filepath.name,
                        "success": False,
                        "error": error_msg,
                    }
                )
    finally:
        _update_batch_progress(
            status="completed",
            current_file="",
            stage="done",
            message="\u6279\u91cf\u5206\u6790\u5df2\u5b8c\u6210",
        )

    success_count = sum(1 for r in results if r.get("success"))
    return jsonify(
        {
            "success": True,
            "results": results,
            "summary": {
                "total": len(filepaths),
                "success": success_count,
                "failed": len(filepaths) - success_count,
            },
        }
    )


@app.route("/download_batch_zip", methods=["POST"])
def download_batch_zip():
    data = _json_payload()
    output_dirs = data.get("output_dirs", [])
    if not isinstance(output_dirs, list) or not output_dirs:
        return jsonify({"error": "没有输出目录"}), 400

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for raw_output_dir in output_dirs:
            try:
                output_path = _resolve_output_dir(raw_output_dir, must_exist=True)
            except (ValueError, FileNotFoundError):
                continue

            base_name = output_path.name
            md_file = output_path / "operation_guide.md"
            pdf_file = output_path / "operation_guide.pdf"
            images_dir = output_path / "images"

            if md_file.exists():
                zf.write(md_file, f"{base_name}/operation_guide.md")
            if pdf_file.exists():
                zf.write(pdf_file, f"{base_name}/operation_guide.pdf")
            if images_dir.exists():
                for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    for img_file in images_dir.glob(pattern):
                        zf.write(img_file, f"{base_name}/images/{img_file.name}")

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="batch_results.zip",
    )


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes"}
    app.run(debug=debug_mode, port=5000)

