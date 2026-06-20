"""Path-safety helpers shared by app.py and service modules.

Resolve and validate user-supplied paths against the configured upload /
output roots, preventing traversal outside the allowed directories.
"""

from pathlib import Path
from typing import Any

from config import OUTPUT_ROOT, UPLOAD_ROOT


def _assert_within(path: Path, root: Path, field_name: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{field_name} 不在允许目录内") from exc


def _resolve_upload_filepath(raw_path: Any) -> Path:
    if not raw_path:
        raise ValueError("文件路径不能为空")
    path = Path(str(raw_path)).expanduser().resolve(strict=False)
    _assert_within(path, UPLOAD_ROOT, "filepath")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("文件不存在")
    return path


def _resolve_output_dir(raw_output_dir: Any, must_exist: bool = True) -> Path:
    if not raw_output_dir:
        raise ValueError("输出目录不能为空")
    candidate = Path(str(raw_output_dir))
    if not candidate.is_absolute():
        candidate = OUTPUT_ROOT / candidate
    output_dir = candidate.expanduser().resolve(strict=False)
    _assert_within(output_dir, OUTPUT_ROOT, "output_dir")
    if must_exist and not output_dir.exists():
        raise FileNotFoundError("输出目录不存在")
    return output_dir
