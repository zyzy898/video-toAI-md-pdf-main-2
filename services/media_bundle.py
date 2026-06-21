"""Subtitle parsing/export and output media bundle assembly.

SRT parsing, VTT/TXT rendering, locating output video/subtitle files, and
building the media bundle metadata + zip payload for an output directory.
"""

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from werkzeug.utils import secure_filename

from config import ALLOWED_EXTENSIONS, OUTPUT_ROOT, WEB_PREVIEW_BASENAME, allowed_file
from path_utils import _assert_within
from utils import _safe_float
from asr.zh_simplify import to_simplified


def _format_seconds_to_mmss(value: Any) -> str:
    seconds = int(max(0.0, _safe_float(value, 0.0, 0.0)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _format_seconds_to_vtt_timestamp(value: Any) -> str:
    seconds = max(0.0, _safe_float(value, 0.0, 0.0))
    whole = int(seconds)
    milli = int(round((seconds - whole) * 1000))
    if milli >= 1000:
        whole += 1
        milli = 0
    hh = whole // 3600
    mm = (whole % 3600) // 60
    ss = whole % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{milli:03d}"


def _parse_srt_timestamp_to_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    match = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})(?:[,.](\d{1,3}))?$", text)
    if not match:
        return None
    hh = int(match.group(1))
    mm = int(match.group(2))
    ss = int(match.group(3))
    ms_raw = str(match.group(4) or "0")
    ms_text = ms_raw.ljust(3, "0")[:3]
    ms = int(ms_text)
    return float(hh * 3600 + mm * 60 + ss) + float(ms) / 1000.0


def _parse_srt_file_entries(srt_path: Path) -> List[Dict[str, Any]]:
    if not srt_path.exists() or not srt_path.is_file():
        return []

    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    blocks = re.split(r"\n{2,}", content.strip())
    entries: List[Dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip("\ufeff").rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        time_line_index = -1
        for idx, line in enumerate(lines):
            if "-->" in line:
                time_line_index = idx
                break
        if time_line_index < 0:
            continue

        timing_line = lines[time_line_index]
        timing_parts = [part.strip() for part in timing_line.split("-->", 1)]
        if len(timing_parts) != 2:
            continue

        start_text = timing_parts[0]
        end_text = timing_parts[1]
        start_seconds = _parse_srt_timestamp_to_seconds(start_text)
        end_seconds = _parse_srt_timestamp_to_seconds(end_text)
        if start_seconds is None or end_seconds is None:
            continue

        text_lines = lines[time_line_index + 1 :]
        text = to_simplified("\n".join(text_lines).strip())
        entries.append(
            {
                "index": len(entries) + 1,
                "start_time": start_text.replace(".", ","),
                "end_time": end_text.replace(".", ","),
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "text": text,
            }
        )

    return entries


def _find_output_subtitle_file(output_dir: Path) -> Path | None:
    candidates: List[Tuple[float, Path]] = []
    for path in output_dir.glob("*.srt"):
        resolved = path.resolve(strict=False)
        if resolved.is_symlink() or not resolved.is_file():
            continue
        try:
            mtime = resolved.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((mtime, resolved))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _find_output_video_file(output_dir: Path, preferred_video_name: str = "") -> Path | None:
    preferred_name = secure_filename(str(preferred_video_name or "").strip())
    if preferred_name:
        preferred_path = (output_dir / preferred_name).resolve(strict=False)
        if (
            preferred_path.exists()
            and preferred_path.is_file()
            and not preferred_path.is_symlink()
            and allowed_file(preferred_path.name)
        ):
            return preferred_path

    candidates: List[Tuple[float, Path]] = []
    for ext in ALLOWED_EXTENSIONS:
        for path in output_dir.glob(f"*.{ext}"):
            # The generated web preview is a derivative, not the source video.
            if path.name == WEB_PREVIEW_BASENAME:
                continue
            resolved = path.resolve(strict=False)
            if resolved.is_symlink() or not resolved.is_file():
                continue
            try:
                mtime = resolved.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, resolved))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _find_web_preview_video(output_dir: Path) -> Path | None:
    preview_path = (output_dir / WEB_PREVIEW_BASENAME).resolve(strict=False)
    if (
        preview_path.exists()
        and preview_path.is_file()
        and not preview_path.is_symlink()
        and preview_path.stat().st_size > 0
    ):
        return preview_path
    return None


def _should_refresh_export_file(target_path: Path, source_path: Path) -> bool:
    if not target_path.exists():
        return True
    try:
        return target_path.stat().st_mtime < source_path.stat().st_mtime
    except OSError:
        return True


def _render_vtt_from_entries(entries: List[Dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    for item in entries:
        start_ts = _format_seconds_to_vtt_timestamp(item.get("start_seconds", 0.0))
        end_ts = _format_seconds_to_vtt_timestamp(item.get("end_seconds", 0.0))
        text = str(item.get("text", "")).strip()
        lines.append(str(item.get("index", "")))
        lines.append(f"{start_ts} --> {end_ts}")
        lines.extend(text.splitlines() if text else [""])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_txt_from_entries(entries: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for item in entries:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        lines.append(f"[{_format_seconds_to_mmss(item.get('start_seconds', 0.0))}] {text}")
    return "\n".join(lines).strip() + ("\n" if lines else "")


def _ensure_subtitle_simplified(srt_path: Path) -> None:
    """Rewrite the SRT file in Simplified Chinese if it contains Traditional.

    Covers SRT files that did not pass through the ASR backend (e.g. uploaded
    by the user). Character-level conversion preserves the SRT layout exactly.
    """

    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    converted = to_simplified(content)
    if converted != content:
        try:
            srt_path.write_text(converted, encoding="utf-8")
        except OSError:
            return


def _ensure_subtitle_exports(output_dir: Path, srt_path: Path) -> Dict[str, Path]:
    output_dir_resolved = output_dir.resolve(strict=False)
    srt_resolved = srt_path.resolve(strict=False)
    _assert_within(output_dir_resolved, OUTPUT_ROOT, "output_dir")
    _assert_within(srt_resolved, output_dir_resolved, "subtitle_file")

    _ensure_subtitle_simplified(srt_resolved)

    entries = _parse_srt_file_entries(srt_resolved)
    vtt_path = srt_resolved.with_suffix(".vtt")
    txt_path = srt_resolved.with_suffix(".txt")

    if _should_refresh_export_file(vtt_path, srt_resolved):
        vtt_path.write_text(_render_vtt_from_entries(entries), encoding="utf-8")
    if _should_refresh_export_file(txt_path, srt_resolved):
        txt_path.write_text(_render_txt_from_entries(entries), encoding="utf-8")

    return {"srt": srt_resolved, "vtt": vtt_path, "txt": txt_path}


def _build_output_media_bundle(
    output_dir: Path,
    preferred_video_name: str = "",
    preferred_srt_path: str = "",
) -> Dict[str, Any]:
    output_dir_resolved = output_dir.resolve(strict=False)
    _assert_within(output_dir_resolved, OUTPUT_ROOT, "output_dir")

    bundle: Dict[str, Any] = {
        "output_dir_name": output_dir_resolved.name,
        "subtitle_available": False,
        "subtitle_line_count": 0,
    }
    output_dir_name_encoded = quote(output_dir_resolved.name)

    video_file = _find_output_video_file(
        output_dir_resolved, preferred_video_name=preferred_video_name
    )
    if video_file is not None:
        bundle["video_file_name"] = video_file.name
        # Prefer the web-optimized preview (H.264 + faststart) for playback;
        # the original file stays in the output dir and is reported separately
        # via video_file_name.
        preview_file = _find_web_preview_video(output_dir_resolved)
        playback_file = preview_file if preview_file is not None else video_file
        bundle["video_preview_optimized"] = preview_file is not None
        bundle["video_preview_url"] = (
            f"/output/{output_dir_name_encoded}/{quote(playback_file.name)}"
        )

    preferred_srt = str(preferred_srt_path or "").strip()
    subtitle_file: Path | None = None
    if preferred_srt:
        candidate = Path(preferred_srt).resolve(strict=False)
        if (
            candidate.exists()
            and candidate.is_file()
            and not candidate.is_symlink()
            and candidate.suffix.lower() == ".srt"
        ):
            try:
                _assert_within(candidate, output_dir_resolved, "subtitle_file")
                subtitle_file = candidate
            except ValueError:
                subtitle_file = None
    if subtitle_file is None:
        subtitle_file = _find_output_subtitle_file(output_dir_resolved)

    if subtitle_file is None:
        return bundle

    exports = _ensure_subtitle_exports(output_dir_resolved, subtitle_file)
    entries = _parse_srt_file_entries(exports["srt"])
    export_urls = {
        fmt: f"/download_subtitle/{output_dir_name_encoded}?format={fmt}"
        for fmt in exports.keys()
    }
    bundle.update(
        {
            "subtitle_available": True,
            "subtitle_file_name": subtitle_file.name,
            "subtitle_line_count": len(entries),
            "subtitle_exports": export_urls,
            "subtitle_workbench_url": f"/subtitle_workbench?output_dir={output_dir_name_encoded}",
        }
    )
    return bundle


def _append_output_bundle_to_zip(
    zf: zipfile.ZipFile, output_path: Path, prefix: str = ""
) -> None:
    md_file = output_path / "operation_guide.md"
    pdf_file = output_path / "operation_guide.pdf"
    images_dir = output_path / "images"

    if md_file.exists():
        zf.write(md_file, f"{prefix}operation_guide.md")
    if pdf_file.exists():
        zf.write(pdf_file, f"{prefix}operation_guide.pdf")
    if images_dir.exists():
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            for img_file in images_dir.glob(pattern):
                zf.write(img_file, f"{prefix}images/{img_file.name}")

    subtitle_file = _find_output_subtitle_file(output_path)
    if subtitle_file is not None:
        subtitle_exports = _ensure_subtitle_exports(output_path, subtitle_file)
        for fmt, export_path in subtitle_exports.items():
            zf.write(export_path, f"{prefix}subtitle.{fmt}")

