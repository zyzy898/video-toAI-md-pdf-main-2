"""Pure helpers for scrape configuration and response diagnostics."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def parse_env_mapping(raw_value: str) -> Dict[str, str]:
    """Parse JSON or ``KEY=VALUE`` env text into a normalized string mapping."""
    text = str(raw_value or "").strip()
    if not text:
        return {}

    parsed: Dict[str, Any] = {}
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        parsed = data
    else:
        parsed = {}
        for token in re.split(r"[;\n]+", text):
            part = str(token or "").strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            key_text = str(key or "").strip()
            value_text = str(value or "").strip()
            if key_text:
                parsed[key_text] = value_text

    normalized: Dict[str, str] = {}
    for key, value in parsed.items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and value_text:
            normalized[key_text] = value_text
    return normalized


def detect_human_verification_signals(
    status_code: int,
    final_url: str,
    html_text: str,
) -> List[str]:
    """Detect common captcha/challenge hints from a scrape response."""
    signals: List[str] = []
    if status_code in {403, 429, 503}:
        signals.append(f"http_{status_code}")

    final_url_lower = str(final_url or "").strip().lower()
    if any(token in final_url_lower for token in ("captcha", "challenge", "verify", "security")):
        signals.append("url_challenge_hint")

    snapshot = str(html_text or "").lower()[:120000]
    pattern_map = {
        "captcha": r"\bcaptcha\b",
        "turnstile": r"\bturnstile\b",
        "cf_challenge": r"cf[-_]?challenge|cloudflare",
        "human_check_en": r"verify you are human|security check|access denied",
        "human_check_zh": "\u4eba\u673a\u9a8c\u8bc1|\u5b89\u5168\u9a8c\u8bc1|\u8bf7\u5b8c\u6210\u9a8c\u8bc1|\u6ed1\u5757\u9a8c\u8bc1|\u884c\u4e3a\u9a8c\u8bc1|\u98ce\u63a7\u6821\u9a8c",
    }
    for label, pattern in pattern_map.items():
        if re.search(pattern, snapshot, flags=re.IGNORECASE):
            signals.append(label)

    unique: List[str] = []
    for item in signals:
        text = str(item or "").strip()
        if text and text not in unique:
            unique.append(text)
    return unique[:8]
