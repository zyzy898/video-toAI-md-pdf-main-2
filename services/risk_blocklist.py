"""Risk blocklist service.

Maintains an on-disk SHA-256 fingerprint blocklist of videos that were
hard-blocked by content moderation, with match/register operations guarded
by a caller-supplied lock.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List

from utils import _safe_int


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
