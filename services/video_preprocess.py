"""Long-video preprocessing: transcode, slice, concat to a lighter proxy.

Builds a low-resolution / low-fps analysis proxy for long videos to reduce
CPU/IO load during analysis. Pure ffmpeg orchestration plus config-driven
thresholds; uses a module-level logger.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import (
    LONG_VIDEO_PREPROCESS_AUDIO_BITRATE,
    LONG_VIDEO_PREPROCESS_CRF,
    LONG_VIDEO_PREPROCESS_ENABLED,
    LONG_VIDEO_PREPROCESS_MAX_SLICES,
    LONG_VIDEO_PREPROCESS_MAX_WIDTH,
    LONG_VIDEO_PREPROCESS_MIN_DURATION_SECONDS,
    LONG_VIDEO_PREPROCESS_MIN_FILE_SIZE_MB,
    LONG_VIDEO_PREPROCESS_PRESET,
    LONG_VIDEO_PREPROCESS_SLICE_SECONDS,
    LONG_VIDEO_PREPROCESS_TARGET_FPS,
    WEB_PREVIEW_AUDIO_BITRATE,
    WEB_PREVIEW_CRF,
    WEB_PREVIEW_ENABLED,
    WEB_PREVIEW_MAX_LONG_EDGE,
    WEB_PREVIEW_PRESET,
    WEB_PREVIEW_SKIP_BELOW_MB,
)
from services.segment_policy import _probe_video_duration_seconds
from video_analyzer_agent import VideoAnalyzerAgent

logger = logging.getLogger(__name__)


def _format_ffmpeg_seconds(seconds: float) -> str:
    safe_seconds = max(0.0, float(seconds or 0.0))
    text = f"{safe_seconds:.3f}"
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _run_video_transcode_for_analysis(
    ffmpeg_cmd: str,
    input_path: Path,
    output_path: Path,
    *,
    start_seconds: float | None = None,
    duration_seconds: float | None = None,
) -> Tuple[bool, str]:
    """
    转码为更轻量的分析副本（低分辨率/低帧率/低音频码率）。
    先尝试 libx264，失败后回退 mpeg4，提升兼容性。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf_expr = (
        f"scale='min({int(LONG_VIDEO_PREPROCESS_MAX_WIDTH)},iw)':-2:flags=lanczos,"
        f"fps={max(1, int(LONG_VIDEO_PREPROCESS_TARGET_FPS))}"
    )

    codec_profiles: List[Tuple[str, List[str]]] = [
        (
            "libx264",
            [
                "-crf",
                str(max(18, int(LONG_VIDEO_PREPROCESS_CRF))),
                "-pix_fmt",
                "yuv420p",
            ],
        ),
        (
            "mpeg4",
            [
                "-q:v",
                "5",
            ],
        ),
    ]

    last_error = "unknown ffmpeg error"
    for video_codec, video_codec_args in codec_profiles:
        cmd: List[str] = [str(ffmpeg_cmd or "ffmpeg"), "-y"]
        if start_seconds is not None and float(start_seconds) > 0:
            cmd.extend(["-ss", _format_ffmpeg_seconds(float(start_seconds))])
        if duration_seconds is not None and float(duration_seconds) > 0:
            cmd.extend(["-t", _format_ffmpeg_seconds(float(duration_seconds))])
        cmd.extend(
            [
                "-i",
                str(input_path),
                "-vf",
                vf_expr,
                "-analyzeduration",
                "32M",
                "-probesize",
                "32M",
                "-c:v",
                video_codec,
                *video_codec_args,
                "-c:a",
                "aac",
                "-b:a",
                str(LONG_VIDEO_PREPROCESS_AUDIO_BITRATE),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        if video_codec == "libx264":
            cmd.insert(cmd.index("-c:a"), "-preset")
            cmd.insert(cmd.index("-c:a"), str(LONG_VIDEO_PREPROCESS_PRESET))

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except Exception as exc:
            last_error = str(exc)
            continue

        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return True, ""

        stderr_tail = (result.stderr or "").strip()[-300:]
        last_error = f"codec={video_codec}, rc={result.returncode}, stderr={stderr_tail}"

    return False, last_error


def _build_ffmpeg_concat_file(list_path: Path, video_paths: List[Path]) -> None:
    lines: List[str] = []
    for path in video_paths:
        normalized = str(path.resolve(strict=False)).replace("\\", "/")
        escaped = normalized.replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _concat_preprocessed_video_chunks(
    ffmpeg_cmd: str, chunk_paths: List[Path], output_path: Path
) -> Tuple[bool, str]:
    if not chunk_paths:
        return False, "empty chunk list"

    concat_list_path = output_path.parent / "concat_list.txt"
    _build_ffmpeg_concat_file(concat_list_path, chunk_paths)

    copy_cmd = [
        str(ffmpeg_cmd or "ffmpeg"),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            copy_cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return True, ""
    except Exception as exc:
        logger.warning("Preprocess concat(copy) 执行异常: %s", exc)

    # 回退到重编码拼接，兼容更多时间基/容器差异。
    reencode_cmd = [
        str(ffmpeg_cmd or "ffmpeg"),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-vf",
        (
            f"scale='min({int(LONG_VIDEO_PREPROCESS_MAX_WIDTH)},iw)':-2:flags=lanczos,"
            f"fps={max(1, int(LONG_VIDEO_PREPROCESS_TARGET_FPS))}"
        ),
        "-c:v",
        "libx264",
        "-crf",
        str(max(18, int(LONG_VIDEO_PREPROCESS_CRF))),
        "-preset",
        str(LONG_VIDEO_PREPROCESS_PRESET),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        str(LONG_VIDEO_PREPROCESS_AUDIO_BITRATE),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        result = subprocess.run(
            reencode_cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return True, ""

    stderr_tail = (result.stderr or "").strip()[-320:]
    return False, f"concat re-encode failed: rc={result.returncode}, stderr={stderr_tail}"


def _prepare_long_video_analysis_source(
    *,
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
) -> Tuple[Path, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "enabled": False,
        "used": False,
        "strategy": "",
        "reason": "",
        "duration_seconds": None,
        "original_size_mb": 0.0,
        "optimized_size_mb": 0.0,
        "slice_count": 0,
        "slice_seconds": int(LONG_VIDEO_PREPROCESS_SLICE_SECONDS),
    }
    if not LONG_VIDEO_PREPROCESS_ENABLED:
        meta["reason"] = "disabled_by_config"
        return video_path, meta

    try:
        original_size_bytes = int(video_path.stat().st_size)
    except OSError:
        original_size_bytes = 0
    original_size_mb = float(original_size_bytes) / (1024.0 * 1024.0)
    meta["original_size_mb"] = round(original_size_mb, 2)

    ffmpeg_cmd = str(getattr(agent, "ffmpeg_cmd", "")).strip() or "ffmpeg"
    duration_seconds = _probe_video_duration_seconds(video_path, ffmpeg_cmd=ffmpeg_cmd)
    if duration_seconds is not None:
        meta["duration_seconds"] = round(float(duration_seconds), 2)

    should_preprocess_by_duration = (
        duration_seconds is not None
        and float(duration_seconds) > float(LONG_VIDEO_PREPROCESS_MIN_DURATION_SECONDS)
    )
    should_preprocess_by_size = (
        original_size_mb > float(LONG_VIDEO_PREPROCESS_MIN_FILE_SIZE_MB)
    )
    if not should_preprocess_by_duration and not should_preprocess_by_size:
        meta["reason"] = "below_threshold"
        return video_path, meta

    preprocess_dir = output_dir / ".analysis_proxy"
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    final_proxy_path = preprocess_dir / video_path.name
    meta["enabled"] = True

    slice_seconds = max(120, int(LONG_VIDEO_PREPROCESS_SLICE_SECONDS))
    max_slices = max(1, int(LONG_VIDEO_PREPROCESS_MAX_SLICES))

    # 长视频优先切片后压缩，降低单次转码压力并提升失败可恢复性。
    if duration_seconds is not None and float(duration_seconds) > float(slice_seconds):
        total_slices = int((float(duration_seconds) + float(slice_seconds) - 1) // float(slice_seconds))
        if total_slices > max_slices:
            slice_seconds = max(slice_seconds, int(float(duration_seconds) // float(max_slices)) + 1)
            total_slices = int((float(duration_seconds) + float(slice_seconds) - 1) // float(slice_seconds))

        chunk_paths: List[Path] = []
        for idx in range(total_slices):
            start_second = float(idx * slice_seconds)
            if duration_seconds is not None and start_second >= float(duration_seconds):
                break
            clip_duration = float(slice_seconds)
            if duration_seconds is not None:
                clip_duration = max(1.0, min(clip_duration, float(duration_seconds) - start_second))

            chunk_output = preprocess_dir / f"chunk_{idx:03d}.mp4"
            ok, err_text = _run_video_transcode_for_analysis(
                ffmpeg_cmd=ffmpeg_cmd,
                input_path=video_path,
                output_path=chunk_output,
                start_seconds=start_second,
                duration_seconds=clip_duration,
            )
            if not ok:
                logger.warning(
                    "长视频切片转码失败，回退原视频: index=%s start=%ss duration=%ss err=%s",
                    idx,
                    _format_ffmpeg_seconds(start_second),
                    _format_ffmpeg_seconds(clip_duration),
                    err_text,
                )
                meta["reason"] = f"slice_transcode_failed:{idx}"
                return video_path, meta
            chunk_paths.append(chunk_output)

        if not chunk_paths:
            meta["reason"] = "slice_generation_empty"
            return video_path, meta

        if len(chunk_paths) == 1:
            shutil.copy2(chunk_paths[0], final_proxy_path)
            concat_ok, concat_err = True, ""
        else:
            concat_ok, concat_err = _concat_preprocessed_video_chunks(
                ffmpeg_cmd=ffmpeg_cmd,
                chunk_paths=chunk_paths,
                output_path=final_proxy_path,
            )
        if not concat_ok:
            logger.warning("长视频切片拼接失败，回退原视频: %s", concat_err)
            meta["reason"] = "slice_concat_failed"
            return video_path, meta

        meta["strategy"] = "slice_then_compress"
        meta["slice_count"] = len(chunk_paths)
        meta["slice_seconds"] = int(slice_seconds)
    else:
        ok, err_text = _run_video_transcode_for_analysis(
            ffmpeg_cmd=ffmpeg_cmd,
            input_path=video_path,
            output_path=final_proxy_path,
        )
        if not ok:
            logger.warning("长视频压缩失败，回退原视频: %s", err_text)
            meta["reason"] = "direct_compress_failed"
            return video_path, meta
        meta["strategy"] = "direct_compress"
        meta["slice_count"] = 1

    if not final_proxy_path.exists():
        meta["reason"] = "proxy_missing"
        return video_path, meta

    try:
        optimized_size_mb = float(final_proxy_path.stat().st_size) / (1024.0 * 1024.0)
    except OSError:
        optimized_size_mb = 0.0
    meta["optimized_size_mb"] = round(optimized_size_mb, 2)
    meta["used"] = True
    meta["reason"] = "ok"
    return final_proxy_path, meta


def _build_web_preview_scale_filter(max_long_edge: int) -> str:
    """Downscale so the longest edge <= max_long_edge, preserving aspect ratio.

    Only scales down (never up) and keeps both dimensions even for yuv420p.
    Handles landscape and portrait sources via a single expression.
    """
    edge = max(2, int(max_long_edge))
    # If width >= height, cap width to `edge`; otherwise cap height to `edge`.
    target_w = f"if(gte(iw,ih),min({edge},iw),-2)"
    target_h = f"if(gte(iw,ih),-2,min({edge},ih))"
    return f"scale='{target_w}':'{target_h}':flags=lanczos"


def generate_web_preview_video(
    *,
    ffmpeg_cmd: str,
    source_path: Path,
    output_path: Path,
) -> Tuple[bool, Dict[str, Any]]:
    """Produce a web-friendly H.264 + faststart preview for browser playback.

    Returns (ok, meta). On failure callers should fall back to the original
    video. The moov atom is moved to the front (+faststart) so HTML5 <video>
    can start playback and seek without buffering the whole file.
    """
    meta: Dict[str, Any] = {
        "enabled": bool(WEB_PREVIEW_ENABLED),
        "used": False,
        "reason": "",
        "source_size_mb": 0.0,
        "preview_size_mb": 0.0,
    }
    if not WEB_PREVIEW_ENABLED:
        meta["reason"] = "disabled_by_config"
        return False, meta

    if not source_path.exists() or not source_path.is_file():
        meta["reason"] = "source_missing"
        return False, meta

    try:
        source_size_mb = float(source_path.stat().st_size) / (1024.0 * 1024.0)
    except OSError:
        source_size_mb = 0.0
    meta["source_size_mb"] = round(source_size_mb, 2)

    if source_size_mb > 0 and source_size_mb < float(WEB_PREVIEW_SKIP_BELOW_MB):
        meta["reason"] = "below_skip_threshold"
        return False, meta

    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf_expr = _build_web_preview_scale_filter(int(WEB_PREVIEW_MAX_LONG_EDGE))

    cmd: List[str] = [
        str(ffmpeg_cmd or "ffmpeg"),
        "-y",
        "-i",
        str(source_path),
        "-vf",
        vf_expr,
        "-c:v",
        "libx264",
        "-preset",
        str(WEB_PREVIEW_PRESET),
        "-crf",
        str(max(18, int(WEB_PREVIEW_CRF))),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        str(WEB_PREVIEW_AUDIO_BITRATE),
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        meta["reason"] = f"ffmpeg_exception:{exc}"
        return False, meta

    if not (result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0):
        stderr_tail = (result.stderr or "").strip()[-300:]
        meta["reason"] = f"ffmpeg_failed:rc={result.returncode},stderr={stderr_tail}"
        # Drop any partial/zero-byte artifact so it never gets served.
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
        return False, meta

    try:
        preview_size_mb = float(output_path.stat().st_size) / (1024.0 * 1024.0)
    except OSError:
        preview_size_mb = 0.0
    meta["preview_size_mb"] = round(preview_size_mb, 2)
    meta["used"] = True
    meta["reason"] = "ok"
    return True, meta
