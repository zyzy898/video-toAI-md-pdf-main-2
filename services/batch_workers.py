"""Batch analysis worker-count resolution helpers."""

from __future__ import annotations

from typing import Any

from utils import _safe_int


def resolve_batch_analyze_workers(
    *,
    total_files: int,
    raw_workers: Any,
    default_workers: int,
    cpu_count: int | None,
) -> int:
    """Resolve a safe worker count bounded by config, CPU count, and file count."""
    workers = _safe_int(raw_workers, default_workers, 1, 16)
    cpu_cap = max(1, int(cpu_count or 1))
    file_cap = max(1, int(total_files or 1))
    return max(1, min(workers, cpu_cap, file_cap))
