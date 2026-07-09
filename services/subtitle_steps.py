from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from services.text_helpers import compact_text
from utils import _safe_float

_ACTION_VERBS = (
    "\u6253\u5f00",
    "\u70b9\u51fb",
    "\u9009\u62e9",
    "\u8f93\u5165",
    "\u641c\u7d22",
    "\u5207\u6362",
    "\u8fdb\u5165",
    "\u521b\u5efa",
    "\u65b0\u589e",
    "\u5220\u9664",
    "\u4fee\u6539",
    "\u7f16\u8f91",
    "\u4fdd\u5b58",
    "\u63d0\u4ea4",
    "\u4e0a\u4f20",
    "\u4e0b\u8f7d",
    "\u5bfc\u51fa",
    "\u590d\u5236",
    "\u7c98\u8d34",
    "\u62d6\u52a8",
    "\u8c03\u6574",
    "\u8bbe\u7f6e",
    "\u52fe\u9009",
    "\u53d6\u6d88",
    "\u786e\u8ba4",
    "\u542f\u52a8",
    "\u8fd0\u884c",
)
_TRAILING_SPLIT_RE = re.compile(r"[\uff0c\u3002\uff01\uff1f\uff1b,.!?;\uff1a:\n]")
_LEADING_FILLER_RE = re.compile(
    r"^(\u4e86|\u4e00\u4e0b|\u4e00\u4e0b\u5b50|\u5e76|\u7136\u540e|"
    r"\u518d|\u518d\u53bb|\u5c06|\u628a|\u5bf9|\u7ed9|\u5230|\u4e3a|"
    r"\u5411|\u4e8e|\u5728|\u901a\u8fc7|\u8fdb\u884c|\u5b8c\u6210)\s*"
)


def _format_seconds_to_mmss(value: Any) -> str:
    seconds = int(max(0.0, _safe_float(value, 0.0, 0.0)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def extract_action_phrase_from_subtitle(text: Any) -> Tuple[str, str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return "", ""

    for verb in _ACTION_VERBS:
        idx = normalized.find(verb)
        if idx < 0:
            continue
        tail = normalized[idx + len(verb) :].strip()
        tail = _TRAILING_SPLIT_RE.split(tail, maxsplit=1)[0].strip()
        tail = _LEADING_FILLER_RE.sub("", tail)
        return verb, compact_text(tail, 16)
    return "", ""


def pick_timeline_points_from_subtitles(
    subtitles: Iterable[Any],
    *,
    minimum: int = 3,
    max_steps: int = 5,
) -> List[Dict[str, Any]]:
    valid_items = [
        item
        for item in subtitles
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    ]
    total = len(valid_items)
    if total <= 0:
        return []

    target = max(int(minimum), min(int(max_steps), 5))
    target = min(target, total) if total >= int(minimum) else total
    if target <= 0:
        return []

    segment = float(total) / float(max(1, target))
    selected_indices: List[int] = []
    for idx in range(target):
        center = int(idx * segment + segment / 2.0)
        selected_indices.append(max(0, min(total - 1, center)))
    selected_indices = sorted(set(selected_indices))

    timeline: List[Dict[str, Any]] = []
    for sub_idx in selected_indices:
        item = valid_items[sub_idx]
        start_seconds = _safe_float(item.get("start_seconds"), 0.0, 0.0)
        timeline.append(
            {
                "time": _format_seconds_to_mmss(start_seconds),
                "text": compact_text(item.get("text", ""), 72),
                "start_seconds": start_seconds,
                "raw": item,
            }
        )
    return timeline
