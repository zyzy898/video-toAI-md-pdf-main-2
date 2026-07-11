"""Helpers for constructing collision-free upload and output paths."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from werkzeug.utils import secure_filename


def _timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def sanitize_upload_filename(filename: str, *, fallback_name: str) -> str:
    raw_name = str(filename or "").strip()
    safe_name = secure_filename(raw_name)
    safe_fallback = secure_filename(fallback_name) or "upload.mp4"
    raw_suffix = Path(raw_name).suffix
    safe_suffix = (
        Path(secure_filename(f"upload{raw_suffix}")).suffix if raw_suffix else ""
    )
    if safe_suffix and not Path(safe_name).suffix:
        safe_stem = secure_filename(Path(raw_name).stem) or Path(safe_fallback).stem
        return f"{safe_stem or 'upload'}{safe_suffix}"
    return safe_name or safe_fallback


def build_unique_upload_path(
    filename: str,
    *,
    upload_root: Path,
    now: datetime | None = None,
) -> Path:
    """Return a non-existing upload path under ``upload_root`` for ``filename``."""
    safe_name = sanitize_upload_filename(
        filename,
        fallback_name=f"upload_{_timestamp(now)}.mp4",
    )

    candidate = upload_root / safe_name
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while candidate.exists():
        candidate = upload_root / f"{stem}_{counter}{suffix}"
        counter += 1

    return candidate


def create_unique_output_dir(
    video_path: Path,
    *,
    output_root: Path,
    now: datetime | None = None,
) -> Path:
    """Create and return a collision-free output directory for ``video_path``."""
    base_name = secure_filename(video_path.stem) or "video"
    timestamp = _timestamp(now)
    candidate = output_root / f"{base_name}_{timestamp}"
    counter = 1

    while candidate.exists():
        candidate = output_root / f"{base_name}_{timestamp}_{counter}"
        counter += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate

def build_upload_staging_path(
    filename: str,
    *,
    staging_root: Path,
    token: str,
    now: datetime | None = None,
) -> Path:
    """Return a staging path under ``staging_root`` with a caller-provided token."""
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = f"staging_{_timestamp(now)}.mp4"

    safe_path = Path(safe_name)
    suffix = safe_path.suffix or ".mp4"
    stem = safe_path.stem or "staging"
    safe_token = secure_filename(str(token or "").strip()) or _timestamp(now)
    return staging_root / f"{stem}_{safe_token}{suffix}"

def reason_code_slug(reason_code: str) -> str:
    """Return a filesystem-safe slug for a risk/quarantine reason code."""
    slug = secure_filename(str(reason_code or "").strip().lower()).replace("-", "_")
    return slug or "content_policy"


def build_unique_quarantine_path(
    video_path: Path,
    *,
    quarantine_root: Path,
    reason_code: str,
    now: datetime | None = None,
) -> Path:
    """Create the reason directory and return a non-existing quarantine target path."""
    reason_dir = quarantine_root / reason_code_slug(reason_code)
    reason_dir.mkdir(parents=True, exist_ok=True)

    timestamp = _timestamp(now)
    target = reason_dir / f"{video_path.stem}_{timestamp}{video_path.suffix}"
    counter = 1
    while target.exists():
        target = reason_dir / f"{video_path.stem}_{timestamp}_{counter}{video_path.suffix}"
        counter += 1

    return target

def find_cleanup_output_dirs(filename: str, *, output_root: Path) -> list[Path]:
    """Return existing output directories associated with an uploaded filename."""
    safe_name = secure_filename(filename)
    if not safe_name:
        return []

    stem = Path(safe_name).stem
    cleanup_dirs: list[Path] = []

    legacy_output_dir = output_root / stem
    if legacy_output_dir.exists() and legacy_output_dir.is_dir():
        cleanup_dirs.append(legacy_output_dir)

    stem_prefix = secure_filename(stem)
    if stem_prefix:
        for output_dir in sorted(output_root.glob(f"{stem_prefix}_*")):
            if output_dir.is_dir():
                cleanup_dirs.append(output_dir)

    return cleanup_dirs

