"""Shared SRT file writer.

Both backends emit segments seconds-based; this module formats them into the
SRT subtitle file format the rest of the project consumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .base import SubtitleSegment


def _format_timestamp(seconds: float) -> str:
    """Format a number of seconds as the SRT ``HH:MM:SS,mmm`` timestamp."""

    if seconds is None or seconds < 0:
        seconds = 0.0
    total_ms = int(round(float(seconds) * 1000))
    hours, remainder = divmod(total_ms, 3600 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _serialize_segments(segments: Iterable[SubtitleSegment]) -> str:
    parts: List[str] = []
    index = 1
    for raw in segments:
        text = str(getattr(raw, "text", "") or "").strip()
        if not text:
            continue
        start = float(getattr(raw, "start", 0.0) or 0.0)
        end = float(getattr(raw, "end", start) or start)
        if end < start:
            end = start
        parts.append(str(index))
        parts.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        parts.append(text)
        parts.append("")
        index += 1
    return "\n".join(parts).rstrip() + "\n"


def write_srt_file(target: Path, segments: Iterable[SubtitleSegment]) -> None:
    """Write segments to ``target`` in SRT format (UTF-8, no BOM)."""

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_serialize_segments(segments), encoding="utf-8")
