"""LLM-based subtitle homophone / typo correction (context-aware pass).

faster-whisper produces near-homophone errors that no deterministic rule can
catch without a hand-maintained glossary, e.g. 「帖子」mis-heard as 「铁子」.
A language model, given the *whole* caption context, can tell which character
the speaker meant ("this is a social-media tutorial, so 帖子 not 铁子").

This module owns only the *pure*, side-effect-free pieces so they can be unit
tested without any network call:

  * :func:`build_correction_messages` - turn a batch of subtitle lines into the
    strict system/user prompt pair.
  * :func:`parse_correction_response` - parse the model's JSON reply back into
    ``{id: corrected_text}``.
  * :func:`apply_corrections` - merge corrections onto the originals, rejecting
    any line the model rewrote too aggressively (length-ratio guard) so a
    misbehaving model can never silently destroy a caption.

The actual async LLM call lives on the agent; it feeds batches through these
functions. Everything here degrades safely: on any malformed input the
original text is preserved.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

# A correction that changes the visible length by more than this ratio is
# treated as a rewrite (not a homophone fix) and rejected to protect meaning.
_MAX_LENGTH_DELTA_RATIO = 0.5
# Default lines per LLM call: small enough to keep the model focused, large
# enough to give it surrounding context for disambiguation.
_DEFAULT_BATCH_SIZE = 40

_SYSTEM_PROMPT = (
    "你是中文字幕校对助手。输入是一段语音识别(ASR)生成的字幕，可能含有"
    "同音字、近音字错误（例如把「帖子」识别成「铁子」、「在线」识别成「再现」）。\n"
    "你的唯一任务：仅修正同音字/近音字造成的错别字，使其符合上下文语义。\n"
    "严格遵守：\n"
    "1. 绝对不要改写、润色、扩写、合并、删除任何句子；只在必要时替换个别错字。\n"
    "2. 不要改变标点风格，不要翻译，不要增删信息。\n"
    "3. 如果某行没有错字，原样返回。\n"
    "4. 保持每行的 id 不变。\n"
    '只输出 JSON，格式：{"corrections":[{"id":0,"text":"修正后的文本"}, ...]}，'
    "不要输出任何额外文字。"
)


def chunk_lines(
    lines: List[str], batch_size: int = _DEFAULT_BATCH_SIZE
) -> List[List[Tuple[int, str]]]:
    """Split caption texts into batches of ``(global_index, text)`` tuples."""

    size = max(1, int(batch_size or _DEFAULT_BATCH_SIZE))
    indexed = [(i, str(t or "")) for i, t in enumerate(lines)]
    return [indexed[i : i + size] for i in range(0, len(indexed), size)]


def build_correction_messages(
    batch: List[Tuple[int, str]],
    *,
    glossary: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build the system/user message pair for one batch of subtitle lines.

    ``glossary`` is an optional comma/space separated hint of correct domain
    terms; it is injected so the model knows the intended vocabulary.
    """

    payload = {"lines": [{"id": idx, "text": text} for idx, text in batch]}
    user_parts: List[str] = []
    if glossary and glossary.strip():
        user_parts.append(f"本视频相关的正确术语（供判断参考）：{glossary.strip()}")
    user_parts.append("请校对以下字幕，仅修正同音/近音错别字：")
    user_parts.append(json.dumps(payload, ensure_ascii=False))
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def _strip_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_correction_response(result: str) -> Dict[int, str]:
    """Parse the model reply into ``{id: corrected_text}``.

    Tolerant of code fences and surrounding prose. Returns an empty mapping on
    any parse failure so the caller simply keeps the originals.
    """

    cleaned = _strip_code_fence(result)
    if not cleaned:
        return {}
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}

    items = parsed.get("corrections") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return {}

    out: Dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if "id" not in item or "text" not in item:
            continue
        try:
            idx = int(item["id"])
        except (TypeError, ValueError):
            continue
        text = str(item.get("text", "") or "").strip()
        if text:
            out[idx] = text
    return out


def _is_safe_correction(original: str, corrected: str) -> bool:
    """Reject corrections that look like rewrites rather than typo fixes."""

    original = str(original or "")
    corrected = str(corrected or "")
    if not corrected:
        return False
    if corrected == original:
        return True
    base = max(len(original), 1)
    if abs(len(corrected) - len(original)) / base > _MAX_LENGTH_DELTA_RATIO:
        return False
    return True


def apply_corrections(
    lines: List[str],
    corrections: Dict[int, str],
) -> Tuple[List[str], int]:
    """Return ``(new_lines, num_changed)`` applying only safe corrections.

    Never mutates the input list (immutability contract). A correction is
    skipped when its index is out of range or it fails the rewrite guard.
    """

    result = list(lines)
    changed = 0
    for idx, corrected in corrections.items():
        if idx < 0 or idx >= len(result):
            continue
        original = result[idx]
        if corrected == original:
            continue
        if not _is_safe_correction(original, corrected):
            logging.debug(
                "[subtitle_correct] 拒绝疑似改写: %r -> %r", original, corrected
            )
            continue
        result[idx] = corrected
        changed += 1
    return result, changed


__all__ = [
    "chunk_lines",
    "build_correction_messages",
    "parse_correction_response",
    "apply_corrections",
]
