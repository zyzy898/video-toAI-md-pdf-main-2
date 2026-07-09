from __future__ import annotations

from typing import Any, Dict, Iterable, List

from services.text_helpers import compact_text

_DEFAULT_PADDING_STEPS = (
    (
        "00:00",
        "\u5185\u5bb9\u6982\u89c8",
        "\u5df2\u81ea\u52a8\u8865\u9f50\u57fa\u7840\u6982\u89c8\uff0c\u5e2e\u52a9\u5feb\u901f\u7406\u89e3\u89c6\u9891\u6574\u4f53\u4e3b\u9898\u3002",
    ),
    (
        "00:20",
        "\u5173\u952e\u4fe1\u606f\u63d0\u70bc",
        "\u5df2\u81ea\u52a8\u8865\u9f50\u5173\u952e\u8981\u70b9\uff0c\u5efa\u8bae\u7ed3\u5408\u539f\u89c6\u9891\u8fdb\u884c\u786e\u8ba4\u3002",
    ),
    (
        "00:40",
        "\u4e0b\u4e00\u6b65\u5efa\u8bae",
        "\u53ef\u5207\u6362\u66f4\u5f3a\u6a21\u578b\u6216\u8865\u5145\u5b57\u5e55\u540e\u518d\u6b21\u5206\u6790\uff0c\u4ee5\u63d0\u5347\u6b65\u9aa4\u51c6\u786e\u7387\u3002",
    ),
)


def _default_padding_step(index: int) -> tuple[str, str, str]:
    return _DEFAULT_PADDING_STEPS[min(index, len(_DEFAULT_PADDING_STEPS) - 1)]


def ensure_minimum_step_count(
    steps: Iterable[Dict[str, Any]],
    *,
    min_steps: int = 3,
    reason: str = "",
) -> List[Dict[str, Any]]:
    normalized_steps = list(steps)
    if len(normalized_steps) >= min_steps:
        return normalized_steps

    reason_hint = compact_text(reason, 54)
    while len(normalized_steps) < min_steps:
        idx = len(normalized_steps)
        default_time, default_title, default_desc = _default_padding_step(idx)
        normalized_steps.append(
            {
                "step": idx + 1,
                "time": default_time,
                "title": default_title,
                "description": (
                    f"{default_desc}\uff08{reason_hint}\uff09"
                    if reason_hint and idx == 1
                    else default_desc
                ),
                "confidence": round(max(0.2, 0.3 - idx * 0.03), 2),
                "source": "fallback_padding",
            }
        )
    return normalized_steps
