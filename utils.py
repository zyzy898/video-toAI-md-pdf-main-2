"""Shared pure utility helpers used across app.py and service modules.

These have no project dependencies and are safe to import anywhere
(no risk of circular imports).
"""

from typing import Any


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


def _normalize_risk_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


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


def _risk_decision_rank(decision: Any) -> int:
    order = {"allow": 0, "restrict": 1, "block": 2}
    return order.get(str(decision or "").strip().lower(), 0)


def _risk_decision_from_rank(rank: int) -> str:
    if rank >= 2:
        return "block"
    if rank <= 0:
        return "allow"
    return "restrict"


def _risk_level_from_decision(decision: Any) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized == "block":
        return "high"
    if normalized == "restrict":
        return "medium"
    return "low"


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

