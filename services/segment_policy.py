"""Video segment policy: duration probing and zone classification.

Pure-ish helpers (only ffprobe/ffmpeg subprocess + config thresholds) that
classify a video into standard/long/super_long/trim_required zones and derive
per-file and per-batch upload/analysis policies and processing guardrails.
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import (
    VIDEO_SEGMENT_BATCH_LONG_MAX_FILES,
    VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_FILES,
    VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_TOTAL_DURATION_SECONDS,
    VIDEO_SEGMENT_CROP_REQUIRED_MIN_SIZE_MB,
    VIDEO_SEGMENT_LONG_MAX_DURATION_SECONDS,
    VIDEO_SEGMENT_STANDARD_MAX_DURATION_SECONDS,
    VIDEO_SEGMENT_STANDARD_MAX_SIZE_MB,
    VIDEO_SEGMENT_SUPER_LONG_MAX_DURATION_SECONDS,
    _env_text,
)


def _probe_video_duration_seconds(video_path: Path, ffmpeg_cmd: str = "ffmpeg") -> float | None:
    ffprobe_candidates: List[str] = ["ffprobe"]
    ffmpeg_text = str(ffmpeg_cmd or "").strip()
    if ffmpeg_text:
        ffmpeg_path = Path(ffmpeg_text)
        if ffmpeg_path.is_absolute():
            suffix = ffmpeg_path.suffix.lower()
            ffprobe_name = "ffprobe.exe" if suffix == ".exe" else "ffprobe"
            ffprobe_candidates.insert(0, str(ffmpeg_path.with_name(ffprobe_name)))

    seen: set[str] = set()
    for ffprobe_cmd in ffprobe_candidates:
        cmd_text = str(ffprobe_cmd or "").strip()
        if not cmd_text or cmd_text in seen:
            continue
        seen.add(cmd_text)
        try:
            result = subprocess.run(
                [
                    cmd_text,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=18,
            )
        except Exception:
            continue

        raw_output = (result.stdout or "").strip()
        if not raw_output:
            continue
        try:
            duration = float(raw_output)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration

    try:
        fallback = subprocess.run(
            [ffmpeg_text or "ffmpeg", "-i", str(video_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=18,
        )
        probe_text = f"{fallback.stdout or ''}\n{fallback.stderr or ''}"
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_text)
        if not match:
            return None
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        duration = hours * 3600 + minutes * 60 + seconds
        return duration if duration > 0 else None
    except Exception:
        return None


def _format_duration_brief(duration_seconds: float | None) -> str:
    if duration_seconds is None or duration_seconds <= 0:
        return "未知"
    total = int(max(0, round(float(duration_seconds))))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def _classify_video_segment_zone(duration_seconds: float | None, file_size_mb: float) -> str:
    size_mb = max(0.0, float(file_size_mb or 0.0))
    duration = None if duration_seconds is None else max(0.0, float(duration_seconds))

    if size_mb >= VIDEO_SEGMENT_CROP_REQUIRED_MIN_SIZE_MB:
        return "trim_required"
    if duration is not None and duration > VIDEO_SEGMENT_SUPER_LONG_MAX_DURATION_SECONDS:
        return "trim_required"
    if duration is not None and duration > VIDEO_SEGMENT_LONG_MAX_DURATION_SECONDS:
        return "super_long"
    if (duration is not None and duration > VIDEO_SEGMENT_STANDARD_MAX_DURATION_SECONDS) or (
        size_mb > VIDEO_SEGMENT_STANDARD_MAX_SIZE_MB
    ):
        return "long"
    return "standard"


def _build_video_segment_policy(video_path: Path, ffmpeg_cmd: str = "ffmpeg") -> Dict[str, Any]:
    try:
        size_bytes = int(video_path.stat().st_size)
    except OSError:
        size_bytes = 0
    file_size_mb = float(size_bytes) / (1024.0 * 1024.0)
    duration_seconds = _probe_video_duration_seconds(video_path, ffmpeg_cmd=ffmpeg_cmd)
    zone = _classify_video_segment_zone(duration_seconds, file_size_mb)

    zone_label_map = {
        "standard": "标准区",
        "long": "长视频区",
        "super_long": "超长区",
        "trim_required": "裁剪优先区",
    }
    recommendations: List[str] = []
    allow_upload = True
    allow_batch = True

    if zone == "standard":
        recommendations = [
            "允许正常接收与分析。",
            "批量建议最多 5 个视频，且总时长尽量 <= 60 分钟。",
        ]
    elif zone == "long":
        recommendations = [
            "允许接收，默认走长视频压缩机制。",
            "优先 use_video=false、max_vision=0；必要时改为 summary_only=true。",
            "如果批次含此类视频，整批建议最多 2 个。",
        ]
    elif zone == "super_long":
        allow_batch = False
        recommendations = [
            "建议仅单文件处理，不建议进入批量分析。",
            "强烈建议先裁剪；如不裁剪，至少使用摘要模式或低峰期处理。",
        ]
    else:
        allow_upload = False
        allow_batch = False
        recommendations = [
            "不建议直接进入系统，需先裁剪后再上传。",
            "判定条件：单视频 > 90 分钟，或文件接近/超过 500MB。",
        ]

    policy = {
        "filename": video_path.name,
        "zone": zone,
        "zone_label": zone_label_map.get(zone, "未知区"),
        "duration_seconds": None
        if duration_seconds is None
        else round(max(0.0, float(duration_seconds)), 2),
        "duration_text": _format_duration_brief(duration_seconds),
        "file_size_mb": round(max(0.0, file_size_mb), 2),
        "allow_upload": allow_upload,
        "allow_batch": allow_batch,
        "requires_trim": zone == "trim_required",
        "recommendations": recommendations,
    }
    return policy


def _build_segment_policy_reject_payload(
    policy: Dict[str, Any],
    *,
    code: str,
    error_message: str,
) -> Dict[str, Any]:
    return {
        "error": error_message,
        "code": code,
        "segment_policy": policy,
    }


def _provider_supports_video_understanding() -> bool:
    """Return True when the active provider advertises VIDEO_UNDERSTANDING.

    Lightweight wrapper around ``llm_client.resolve_provider`` so the analyze
    path can preemptively disable ``use_video`` when the current platform is
    known to not support video understanding (e.g. OpenAI / DeepSeek / Qwen).
    The heuristic matches what ``build_llm_client`` would route to.
    """

    try:
        from llm_client import resolve_provider
    except Exception:
        return True  # Fail open; Ark remains the historical default.

    base_url = _env_text(("MODEL_BASE_URL", "RISK_FALLBACK_MODEL_BASE_URL"), "")
    provider_hint = _env_text(("MODEL_PROVIDER",), "")
    return resolve_provider(provider_hint=provider_hint, base_url=base_url) == "ark"


def _apply_video_segment_processing_guardrails(
    policy: Dict[str, Any],
    *,
    use_video: bool,
    web_search: bool,
    max_vision: int,
    summary_only: bool,
) -> Tuple[bool, bool, int, bool, List[str]]:
    zone = str(policy.get("zone", "")).strip().lower()
    adjusted_use_video = bool(use_video)
    adjusted_web_search = bool(web_search)
    adjusted_max_vision = max(0, int(max_vision))
    adjusted_summary_only = bool(summary_only)
    notes: List[str] = []

    if adjusted_use_video and not _provider_supports_video_understanding():
        adjusted_use_video = False
        notes.append(
            "当前模型平台不支持视频理解，已自动切换为字幕分析模式（use_video=false）。"
        )

    if adjusted_web_search and not _provider_supports_video_understanding():
        # web_search tool also relies on Ark's responses.create extension.
        adjusted_web_search = False
        notes.append(
            "当前模型平台不支持联网搜索工具，已自动关闭 web_search。"
        )

    if zone == "long":
        if adjusted_use_video:
            adjusted_use_video = False
            notes.append("长视频区已自动设置 use_video=false 以降低 CPU 压力。")
        if adjusted_max_vision > 0:
            adjusted_max_vision = 0
            notes.append("长视频区已自动设置 max_vision=0 以降低额外视觉开销。")
    elif zone == "super_long":
        if adjusted_use_video:
            adjusted_use_video = False
            notes.append("超长区已自动设置 use_video=false。")
        if adjusted_max_vision > 0:
            adjusted_max_vision = 0
            notes.append("超长区已自动设置 max_vision=0。")
        if not adjusted_summary_only:
            adjusted_summary_only = True
            notes.append("超长区已自动启用 summary_only=true（摘要模式）。")
        if adjusted_web_search:
            adjusted_web_search = False
            notes.append("超长区已自动关闭 web_search 以减少处理时延。")

    return (
        adjusted_use_video,
        adjusted_web_search,
        adjusted_max_vision,
        adjusted_summary_only,
        notes,
    )


def _evaluate_batch_segment_policy(file_policies: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_files = len(file_policies)
    long_policies = [item for item in file_policies if str(item.get("zone", "")).strip() == "long"]
    super_long_policies = [
        item for item in file_policies if str(item.get("zone", "")).strip() == "super_long"
    ]
    trim_required_policies = [
        item for item in file_policies if str(item.get("zone", "")).strip() == "trim_required"
    ]

    known_durations = [
        float(item.get("duration_seconds", 0.0))
        for item in file_policies
        if isinstance(item.get("duration_seconds"), (int, float))
        and float(item.get("duration_seconds", 0.0)) > 0
    ]
    total_duration_seconds = sum(known_durations)
    warnings: List[str] = []

    if trim_required_policies:
        first = trim_required_policies[0]
        return {
            "allowed": False,
            "code": "video_segment_trim_required",
            "error": (
                f"{first.get('filename', '视频')} 属于裁剪优先区（{first.get('duration_text', '未知')} / "
                f"{first.get('file_size_mb', 0)}MB），请先裁剪后再上传分析。"
            ),
            "warnings": warnings,
            "summary": {
                "total_files": total_files,
                "long_count": len(long_policies),
                "super_long_count": len(super_long_policies),
                "trim_required_count": len(trim_required_policies),
                "total_duration_seconds": round(total_duration_seconds, 2),
            },
        }

    if super_long_policies:
        first = super_long_policies[0]
        return {
            "allowed": False,
            "code": "video_segment_super_long_batch_not_allowed",
            "error": (
                f"{first.get('filename', '视频')} 属于超长区（{first.get('duration_text', '未知')}），"
                "建议仅单文件处理，不支持进入批量分析。"
            ),
            "warnings": warnings,
            "summary": {
                "total_files": total_files,
                "long_count": len(long_policies),
                "super_long_count": len(super_long_policies),
                "trim_required_count": len(trim_required_policies),
                "total_duration_seconds": round(total_duration_seconds, 2),
            },
        }

    if long_policies and total_files > VIDEO_SEGMENT_BATCH_LONG_MAX_FILES:
        return {
            "allowed": False,
            "code": "video_segment_long_batch_limit",
            "error": (
                "当前批次包含长视频区内容时，整批最多允许 2 个视频。"
                f"当前数量: {total_files}。"
            ),
            "warnings": warnings,
            "summary": {
                "total_files": total_files,
                "long_count": len(long_policies),
                "super_long_count": len(super_long_policies),
                "trim_required_count": len(trim_required_policies),
                "total_duration_seconds": round(total_duration_seconds, 2),
            },
        }

    if not long_policies and total_files > VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_FILES:
        warnings.append(
            "当前批次为标准区，建议最多 5 个视频；数量过多可能导致整体耗时明显上升。"
        )
    if (
        not long_policies
        and known_durations
        and total_duration_seconds > VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_TOTAL_DURATION_SECONDS
    ):
        warnings.append("当前批次总时长已超过 60 分钟，建议拆分批次以降低峰值负载。")

    return {
        "allowed": True,
        "code": "",
        "error": "",
        "warnings": warnings,
        "summary": {
            "total_files": total_files,
            "long_count": len(long_policies),
            "super_long_count": len(super_long_policies),
            "trim_required_count": len(trim_required_policies),
            "total_duration_seconds": round(total_duration_seconds, 2),
        },
    }
