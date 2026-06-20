"""Subtitle/filename keyword text-risk gate.

Loads the keyword lexicon (cached by mtime), counts hits per dimension, and
derives an allow/restrict/block decision as a fallback when visual moderation
is unavailable. Cache state and lock are module-local.
"""

import json
import logging
import re
import shutil
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Tuple

from config import (
    RISK_KEYWORD_LEXICON_PATH,
    TEXT_RISK_BLOCK_THRESHOLD,
    TEXT_RISK_RESTRICT_THRESHOLD,
)
from video_analyzer_agent import VideoAnalyzerAgent

logger = logging.getLogger(__name__)
risk_keyword_lexicon_lock = RLock()
risk_keyword_lexicon_cache_mtime_ns: int | None = None
risk_keyword_lexicon_cache_data: Dict[str, Dict[str, Any]] | None = None


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

