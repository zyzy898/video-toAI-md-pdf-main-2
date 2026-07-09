from __future__ import annotations

from typing import Any, Dict, Iterable, List

from services.text_helpers import compact_text

_DEFAULT_TIMELINE_TIMES = ("00:00", "00:20", "00:40")
_DEFAULT_TIMELINE_TEXT = "\u5f85\u786e\u8ba4\u7247\u6bb5"
_DEFAULT_KEY_POINT = "00:00\uff1a\u5f85\u786e\u8ba4\u8981\u70b9"


def _default_timeline_time(index: int) -> str:
    if not _DEFAULT_TIMELINE_TIMES:
        return "00:00"
    return _DEFAULT_TIMELINE_TIMES[min(index, len(_DEFAULT_TIMELINE_TIMES) - 1)]


def extract_timeline_from_steps(
    steps: Iterable[Any],
    *,
    limit: int = 5,
    min_steps: int = 3,
) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    capped_limit = max(0, int(limit))
    required_steps = max(0, int(min_steps))

    for item in steps:
        if not isinstance(item, dict):
            continue
        time_text = str(item.get("time", "")).strip()
        title_text = compact_text(item.get("title", ""), 40)
        if not time_text and not title_text:
            continue
        timeline.append({"time": time_text or "00:00", "text": title_text})
        if len(timeline) >= capped_limit:
            break

    while len(timeline) < required_steps:
        timeline.append(
            {
                "time": _default_timeline_time(len(timeline)),
                "text": _DEFAULT_TIMELINE_TEXT,
            }
        )
    return timeline


def build_key_points_from_steps(
    steps: Iterable[Any],
    *,
    limit: int = 5,
    min_points: int = 3,
) -> List[str]:
    key_points: List[str] = []
    capped_limit = max(0, int(limit))
    required_points = max(0, int(min_points))

    for item in steps:
        if not isinstance(item, dict):
            continue
        title_text = compact_text(item.get("title", ""), 24)
        desc_text = compact_text(item.get("description", ""), 48)
        time_text = str(item.get("time", "")).strip() or "00:00"
        if title_text:
            key_points.append(f"{time_text}\uff1a{title_text}")
        elif desc_text:
            key_points.append(f"{time_text}\uff1a{desc_text}")
        if len(key_points) >= capped_limit:
            break

    while len(key_points) < required_points:
        key_points.append(_DEFAULT_KEY_POINT)
    return key_points[:capped_limit]
