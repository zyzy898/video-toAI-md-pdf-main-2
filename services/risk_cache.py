"""Upload risk-result cache service.

Caches content-moderation decisions keyed by (video SHA-256, model policy
signature) so the same video+model combination is not re-moderated within
the TTL window. Access is guarded by a caller-supplied lock.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List

from config import (
    RISK_BLOCK_ON_RESTRICT,
    RISK_BLOCK_THRESHOLD,
    RISK_CRITICAL_SCORE,
    RISK_DIMENSION_HARD_BLOCK_SCORE,
    RISK_RESTRICT_THRESHOLD,
    TEXT_RISK_BLOCK_THRESHOLD,
    TEXT_RISK_RESTRICT_THRESHOLD,
)
from utils import _safe_float, _safe_int
from video_analyzer_agent import VideoAnalyzerAgent


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
