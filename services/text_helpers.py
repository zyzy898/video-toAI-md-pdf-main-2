"""Text normalization helpers."""

from __future__ import annotations

import re
from typing import Any


def compact_text(value: Any, limit: int = 120) -> str:
    """Collapse whitespace and trim text to ``limit`` characters with an ellipsis."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    safe_limit = max(1, int(limit))
    if len(text) <= safe_limit:
        return text
    return text[: max(1, safe_limit - 1)].rstrip() + "\u2026"
