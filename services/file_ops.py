"""Filesystem operation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol


class RemovablePath(Protocol):
    def exists(self) -> bool: ...
    def is_file(self) -> bool: ...
    def unlink(self) -> None: ...


def safe_remove_file(
    path: RemovablePath | Path,
    *,
    on_error: Callable[[RemovablePath | Path, OSError], None] | None = None,
) -> None:
    """Remove ``path`` if it exists and is a file, ignoring missing paths and dirs."""
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError as exc:
        if on_error is not None:
            on_error(path, exc)
