#!/usr/bin/env python3
"""Detect common Chinese mojibake patterns in source files."""

from __future__ import annotations

import sys
from pathlib import Path

# These tokens are frequent UTF-8/GBK mojibake fragments we saw in this project.
SUSPECT_TOKENS = [
    "鏃犳晥",
    "娌℃湁",
    "璇疯緭鍏",
    "涓嶆敮鎸",
    "缂哄皯",
    "瓒呭嚭",
    "鍒嗙墖",
    "妯″瀷",
    "杈撳嚭",
    "鎿嶄綔姝ラ",
    "姝ラ",
    "鍐呭",
    "嫆缁",
    "瀛楀箷",
    "鏈瘑鍒",
    "瑙嗛",
    "鏂囦欢",
    "鍒犻櫎",
]


def _scan_file(path: Path) -> list[str]:
    # Avoid flagging this detector's own token dictionary.
    if path.name == "check_mojibake.py":
        return []

    issues: list[str] = []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"{path}: failed to read file ({exc})"]

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{path}: file is not valid UTF-8 ({exc})"]

    if "\ufffd" in text:
        issues.append(f"{path}: contains replacement character U+FFFD (possible encoding corruption)")

    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        hit = next((token for token in SUSPECT_TOKENS if token in line), None)
        if hit:
            snippet = line.strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            issues.append(f"{path}:{lineno}: suspicious mojibake token '{hit}' -> {snippet}")
    return issues


def main(argv: list[str]) -> int:
    if not argv:
        return 0

    all_issues: list[str] = []
    for raw_path in argv:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        all_issues.extend(_scan_file(path))

    if all_issues:
        _safe_print("Mojibake check failed:")
        for issue in all_issues:
            _safe_print(f"- {issue}")
        _safe_print("Please replace garbled text with intended UTF-8 Chinese/English copy.")
        return 1
    return 0


def _safe_print(text: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    try:
        sys.stdout.buffer.write((text + "\n").encode(encoding, errors="replace"))
    except Exception:
        print(text)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
