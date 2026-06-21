"""Correction feedback loop: log LLM subtitle fixes and feed Plan-A hotwords.

When the LLM homophone pass rewrites a caption (e.g. 「铁子」-> 「帖子」), we want
to *learn* from it:

  1. **Record** every change to a human-reviewable JSONL log, including the
     full before/after line, a timestamp, and - crucially - the jieba word
     segmentation of both sides so a human can see exactly which domain term
     was wrong and verify the fix.
  2. **Distil** the changes into word-level ``(wrong -> right)`` pairs using
     jieba segmentation (so we capture the whole word 「帖子」, not just the
     single changed character 「帖」).
  3. **Accumulate** the correct terms into a plain-text glossary file that
     :mod:`asr.factory` loads back as faster-whisper ``hotwords`` (Plan A), so
     each run biases decoding away from the mistakes seen on previous runs.

Everything here is best-effort and pure where possible: term extraction is a
side-effect-free function (unit tested without disk/LLM), while the persistence
helpers degrade safely and never raise into the transcription path.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional, Tuple

# Default artefact locations (env-overridable). Both live under ``outputs/``.
_DEFAULT_LOG_PATH = Path("outputs") / "subtitle_corrections.jsonl"
_DEFAULT_GLOSSARY_PATH = Path("outputs") / "hotwords_glossary.txt"

# Only CJK-containing terms of >=2 chars are useful domain hotwords; this skips
# punctuation-only or single-char diffs that would just add noise.
_MIN_TERM_LEN = 2
_CJK_RE = re.compile(r"[一-鿿]")

_file_lock = RLock()

try:  # jieba is optional; without it we fall back to char-level pairs.
    import jieba  # type: ignore

    jieba.setLogLevel(logging.WARNING)
except Exception:  # pragma: no cover - exercised only when not installed
    jieba = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pure segmentation / extraction helpers
# ---------------------------------------------------------------------------
def segment(text: str) -> List[str]:
    """Word-segment Chinese ``text`` (jieba when available, else char split)."""

    text = str(text or "")
    if not text:
        return []
    if jieba is None:
        return list(text)
    return [w for w in jieba.cut(text) if w.strip()]


def _segment_spans(text: str) -> List[Tuple[str, int, int]]:
    """Return ``(word, start, end)`` char spans for ``text``."""

    spans: List[Tuple[str, int, int]] = []
    cursor = 0
    tokens = list(jieba.cut(text)) if jieba is not None else list(text)
    for tok in tokens:
        if tok == "":
            continue
        start = text.find(tok, cursor)
        if start < 0:
            start = cursor
        end = start + len(tok)
        spans.append((tok, start, end))
        cursor = end
    return spans


def _overlapping_words(spans: List[Tuple[str, int, int]], lo: int, hi: int) -> str:
    """Join words whose span overlaps the char range ``[lo, hi)``."""

    if hi <= lo:
        # Zero-width change (pure insert/delete): grab the word touching ``lo``.
        hi = lo + 1
    parts = [w for (w, s, e) in spans if s < hi and e > lo]
    return "".join(parts)


def _is_useful_term(term: str) -> bool:
    term = str(term or "").strip()
    return len(term) >= _MIN_TERM_LEN and bool(_CJK_RE.search(term))


def extract_term_pairs(original: str, corrected: str) -> List[Tuple[str, str]]:
    """Extract word-level ``(wrong, right)`` pairs from a single line edit.

    Uses difflib to locate changed char ranges, then expands each range to full
    jieba words on both sides so the *whole* domain term is captured. Returns an
    empty list when nothing meaningful changed.
    """

    original = str(original or "")
    corrected = str(corrected or "")
    if not corrected or original == corrected:
        return []

    orig_spans = _segment_spans(original)
    corr_spans = _segment_spans(corrected)

    pairs: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    matcher = SequenceMatcher(None, original, corrected, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        wrong = _overlapping_words(orig_spans, i1, i2)
        right = _overlapping_words(corr_spans, j1, j2)
        if not _is_useful_term(right) or wrong == right:
            continue
        key = (wrong, right)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((wrong, right))
    return pairs


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def _resolve_path(env_name: str, default: Path) -> Path:
    raw = str(os.getenv(env_name, "")).strip()
    return Path(raw) if raw else default


def log_path() -> Path:
    return _resolve_path("SUBTITLE_CORRECTION_LOG", _DEFAULT_LOG_PATH)


def glossary_path() -> Path:
    return _resolve_path("WHISPER_HOTWORDS_FILE", _DEFAULT_GLOSSARY_PATH)


# ---------------------------------------------------------------------------
# Persistence (best-effort; never raises into the transcription path)
# ---------------------------------------------------------------------------
def _load_glossary_terms(path: Path) -> List[str]:
    """Read existing glossary terms (one per line, ``# wrong -> right`` lines)."""

    if not path.exists():
        return []
    terms: List[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            terms.append(line)
    except OSError:  # pragma: no cover - defensive
        return []
    return terms


def append_glossary_terms(new_terms: List[str], path: Optional[Path] = None) -> List[str]:
    """Merge ``new_terms`` into the hotwords glossary file, deduped + ordered.

    Returns the list of terms that were actually newly added. The glossary is
    a plain UTF-8 file, one correct term per line, loaded back by the factory
    as faster-whisper ``hotwords``.
    """

    target = path or glossary_path()
    with _file_lock:
        existing = _load_glossary_terms(target)
        existing_set = set(existing)
        added = [t for t in dict.fromkeys(new_terms) if t and t not in existing_set]
        if not added:
            return []
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            merged = existing + added
            target.write_text("\n".join(merged) + "\n", encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            logging.warning("[correction_log] 热词表写入失败: %s", exc)
            return []
    return added


def record_corrections(
    changes: List[Dict[str, str]],
    *,
    video: str = "",
    path: Optional[Path] = None,
) -> int:
    """Append one JSONL record per changed line to the review log.

    Each ``change`` is ``{"time", "original", "corrected"}``. The record adds
    jieba segmentation of both sides and the distilled term pairs so a human
    can review exactly what changed and why.
    Returns the number of records written.
    """

    if not changes:
        return 0
    target = path or log_path()
    written = 0
    lines: List[str] = []
    for ch in changes:
        original = str(ch.get("original", "") or "")
        corrected = str(ch.get("corrected", "") or "")
        if not corrected or original == corrected:
            continue
        pairs = extract_term_pairs(original, corrected)
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "video": video,
            "time": str(ch.get("time", "") or ""),
            "original": original,
            "corrected": corrected,
            "original_seg": segment(original),
            "corrected_seg": segment(corrected),
            "term_pairs": [{"wrong": w, "right": r} for w, r in pairs],
        }
        lines.append(json.dumps(record, ensure_ascii=False))
        written += 1

    if not lines:
        return 0
    with _file_lock:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as exc:  # pragma: no cover - defensive
            logging.warning("[correction_log] 纠错日志写入失败: %s", exc)
            return 0
    return written


def harvest_terms(changes: List[Dict[str, str]]) -> List[str]:
    """Collect the distinct *correct* terms from a batch of line changes."""

    out: List[str] = []
    seen: set[str] = set()
    for ch in changes:
        for _wrong, right in extract_term_pairs(
            str(ch.get("original", "") or ""), str(ch.get("corrected", "") or "")
        ):
            if right not in seen:
                seen.add(right)
                out.append(right)
    return out


def record_and_learn(
    changes: List[Dict[str, str]],
    *,
    video: str = "",
) -> Tuple[int, List[str]]:
    """Full feedback step: write the review log AND grow the hotwords glossary.

    Returns ``(records_written, newly_added_hotwords)``.
    """

    written = record_corrections(changes, video=video)
    added = append_glossary_terms(harvest_terms(changes))
    if added:
        logging.info("[correction_log] 新增热词 %s 个: %s", len(added), ", ".join(added))
    return written, added


def load_hotwords(path: Optional[Path] = None) -> str:
    """Return accumulated glossary terms as a single space-joined hotwords str."""

    terms = _load_glossary_terms(path or glossary_path())
    return " ".join(terms)


__all__ = [
    "segment",
    "extract_term_pairs",
    "harvest_terms",
    "record_corrections",
    "append_glossary_terms",
    "record_and_learn",
    "load_hotwords",
    "log_path",
    "glossary_path",
]
