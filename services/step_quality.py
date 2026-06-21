"""Step quality scoring.

Pure heuristics that score extracted steps (structure / temporal / confidence
/ source / count) and combine them into an overall quality score per result
mode. No project state; only config weighting maps and shared utils.
"""

from typing import Any, Dict, List

from config import (
    QUALITY_MODE_CAP,
    QUALITY_MODE_PRIOR,
    QUALITY_REASON_PENALTY_MAP,
    QUALITY_SOURCE_WEIGHT_MAP,
)
from utils import _normalize_risk_score, _safe_float


def _parse_step_time_to_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    direct_number = _safe_float(text, -1.0)
    if direct_number >= 0:
        return direct_number

    normalized = text.replace("：", ":")
    parts = [part.strip() for part in normalized.split(":") if str(part).strip()]
    if len(parts) not in (2, 3):
        return None
    try:
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            if minutes < 0 or seconds < 0:
                return None
            return minutes * 60 + seconds
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        if hours < 0 or minutes < 0 or seconds < 0:
            return None
        return hours * 3600 + minutes * 60 + seconds
    except (TypeError, ValueError):
        return None


def _compute_step_structure_score(steps: List[Dict[str, Any]]) -> float:
    if not steps:
        return 0.0
    total = len(steps)
    title_present = 0
    desc_present = 0
    time_present = 0
    title_richness = 0.0
    desc_richness = 0.0
    for item in steps:
        title = str(item.get("title", "")).strip()
        desc = str(item.get("description", "")).strip()
        time_text = str(item.get("time", "")).strip()
        if title:
            title_present += 1
            title_richness += min(1.0, len(title) / 12.0)
        if desc:
            desc_present += 1
            desc_richness += min(1.0, len(desc) / 40.0)
        if time_text:
            time_present += 1

    title_ratio = title_present / total
    desc_ratio = desc_present / total
    time_ratio = time_present / total
    title_rich = title_richness / total
    desc_rich = desc_richness / total
    score = (
        title_ratio * 0.3
        + desc_ratio * 0.24
        + time_ratio * 0.18
        + title_rich * 0.14
        + desc_rich * 0.14
    )
    return round(max(0.0, min(1.0, score)), 3)


def _compute_step_temporal_score(steps: List[Dict[str, Any]]) -> float:
    if not steps:
        return 0.0
    raw_times = [_parse_step_time_to_seconds(item.get("time")) for item in steps]
    parsed_times = [value for value in raw_times if value is not None]
    parse_ratio = len(parsed_times) / len(steps)
    if len(parsed_times) <= 1:
        base = 0.2 if parse_ratio <= 0 else 0.46
        return round(max(0.0, min(1.0, base)), 3)

    monotonic_hits = sum(
        1 for idx in range(1, len(parsed_times)) if parsed_times[idx] >= parsed_times[idx - 1] - 0.5
    )
    monotonic_ratio = monotonic_hits / (len(parsed_times) - 1)

    unique_ratio = len(set(round(value, 1) for value in parsed_times)) / len(parsed_times)
    spread = max(parsed_times) - min(parsed_times)
    target_spread = max(20.0, (len(parsed_times) - 1) * 12.0)
    spread_ratio = min(1.0, spread / target_spread)

    gap_hits = sum(
        1 for idx in range(1, len(parsed_times)) if (parsed_times[idx] - parsed_times[idx - 1]) >= 1.0
    )
    gap_ratio = gap_hits / (len(parsed_times) - 1)

    score = (
        parse_ratio * 0.22
        + monotonic_ratio * 0.24
        + unique_ratio * 0.22
        + spread_ratio * 0.22
        + gap_ratio * 0.1
    )
    return round(max(0.0, min(1.0, score)), 3)


def _compute_step_confidence_score(steps: List[Dict[str, Any]], result_mode: str) -> float:
    if not steps:
        return 0.0
    confidence_values: List[float] = []
    for item in steps:
        raw_confidence = _safe_float(item.get("confidence"), -1.0)
        if raw_confidence >= 0:
            confidence_values.append(_normalize_risk_score(raw_confidence, 0.0))

    default_by_mode = {
        "steps": 0.74,
        "candidate_steps": 0.48,
        "timeline_summary": 0.34,
    }
    if not confidence_values:
        return round(default_by_mode.get(result_mode, 0.42), 3)

    average = sum(confidence_values) / len(confidence_values)
    variance = sum((value - average) ** 2 for value in confidence_values) / len(confidence_values)
    std_dev = variance ** 0.5
    stability = max(0.0, min(1.0, 1.0 - std_dev / 0.35))
    presence_ratio = len(confidence_values) / len(steps)
    score = average * 0.72 + stability * 0.18 + presence_ratio * 0.1
    return round(max(0.0, min(1.0, score)), 3)


def _compute_step_source_score(steps: List[Dict[str, Any]], result_mode: str) -> float:
    if not steps:
        return 0.0
    source_scores: List[float] = []
    unique_sources: set[str] = set()
    for item in steps:
        source = str(item.get("source", "")).strip().lower()
        if source:
            unique_sources.add(source)
            source_scores.append(QUALITY_SOURCE_WEIGHT_MAP.get(source, 0.72))

    if not source_scores:
        default_by_mode = {
            "steps": 0.76,
            "candidate_steps": 0.5,
            "timeline_summary": 0.34,
        }
        return round(default_by_mode.get(result_mode, 0.52), 3)

    average_score = sum(source_scores) / len(source_scores)
    diversity_bonus = min(0.08, max(0, len(unique_sources) - 1) * 0.03)
    score = average_score + diversity_bonus
    return round(max(0.0, min(1.0, score)), 3)


def _compute_step_count_score(step_count: int, result_mode: str) -> float:
    if step_count <= 0:
        return 0.0
    if result_mode == "steps":
        if 3 <= step_count <= 10:
            return 1.0
        if step_count in (2, 11, 12, 13, 14):
            return 0.78
        return 0.56
    if result_mode == "candidate_steps":
        if 3 <= step_count <= 6:
            return 0.94
        if step_count in (2, 7):
            return 0.76
        return 0.58
    if result_mode == "timeline_summary":
        if 3 <= step_count <= 5:
            return 0.9
        if step_count in (2, 6):
            return 0.7
        return 0.52
    if 3 <= step_count <= 8:
        return 0.85
    if step_count in (2, 9):
        return 0.65
    return 0.5


def _resolve_quality_reason_penalty(degrade_reason: str) -> float:
    normalized_reason = str(degrade_reason or "").strip().lower()
    if not normalized_reason:
        return 0.0
    if normalized_reason in QUALITY_REASON_PENALTY_MAP:
        return QUALITY_REASON_PENALTY_MAP[normalized_reason]
    if "failed" in normalized_reason:
        return 0.12
    if "summary" in normalized_reason:
        return 0.06
    if "candidate" in normalized_reason:
        return 0.05
    return 0.03


def _resolve_quality_score(
    result_mode: str,
    steps: List[Dict[str, Any]],
    fallback_used: bool,
    degrade_reason: str = "",
) -> float:
    normalized_mode = str(result_mode or "steps").strip().lower()
    if normalized_mode == "blocked_notice":
        return 0.0

    valid_steps = [item for item in steps if isinstance(item, dict)]
    if not valid_steps:
        return 0.0

    prior = QUALITY_MODE_PRIOR.get(normalized_mode, 0.46)
    structure_score = _compute_step_structure_score(valid_steps)
    temporal_score = _compute_step_temporal_score(valid_steps)
    confidence_score = _compute_step_confidence_score(valid_steps, normalized_mode)
    source_score = _compute_step_source_score(valid_steps, normalized_mode)
    count_score = _compute_step_count_score(len(valid_steps), normalized_mode)

    score = (
        prior * 0.18
        + structure_score * 0.24
        + temporal_score * 0.18
        + confidence_score * 0.2
        + source_score * 0.1
        + count_score * 0.1
    )

    if fallback_used:
        score -= 0.05 if normalized_mode == "steps" else 0.025

    score -= _resolve_quality_reason_penalty(degrade_reason)
    mode_cap = QUALITY_MODE_CAP.get(normalized_mode, 0.95)
    score = max(0.0, min(mode_cap, score))
    return round(score, 3)

