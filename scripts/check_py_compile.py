#!/usr/bin/env python3
"""Compile changed Python files to catch syntax errors before commit."""

from __future__ import annotations

import py_compile
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    python_files = [Path(item) for item in argv if item.endswith(".py")]
    if not python_files:
        return 0

    failed = False
    for path in python_files:
        if not path.exists() or not path.is_file():
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failed = True
            print(f"[py_compile] {path} failed:\n{exc}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
