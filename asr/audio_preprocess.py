"""Optional ffmpeg audio pre-processing for the ASR stage.

ASR accuracy has a hard ceiling set by input audio quality: background music,
low-frequency rumble and wildly varying loudness all push Whisper toward
wrong/near-homophone tokens. This module runs a cheap ffmpeg filter chain
*before* transcription to clean the signal:

  * ``highpass``  - drop sub-80 Hz rumble (AC hum, handling noise).
  * ``afftdn``    - FFT de-noiser, removes steady background hiss.
  * ``loudnorm``  - EBU R128 loudness normalisation so quiet speech is not
                    swallowed and loud passages are not clipped.

Output is 16 kHz mono PCM WAV - exactly what Whisper resamples to internally,
so we lose nothing by doing it up-front.

Design contract (matches ``zh_simplify`` / ``subtitle_clean``):
  * Best-effort only. If ffmpeg is missing or the filter fails, we return the
    original path so transcription never hard-fails over pre-processing.
  * Pure-ish: no global mutation; the caller owns temp-file cleanup via the
    returned path (use :func:`cleanup_temp_audio`).
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# EBU R128 targets: -16 LUFS integrated is a sane spoken-content loudness.
_DEFAULT_FILTER_CHAIN = "highpass=f=80,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11"
_TARGET_SAMPLE_RATE = "16000"


def _resolve_ffmpeg() -> str:
    """Return a usable ffmpeg executable, preferring the bundled imageio one."""

    try:
        import imageio_ffmpeg  # type: ignore

        exe = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if exe.exists():
            return str(exe)
    except Exception:  # pragma: no cover - falls back to PATH ffmpeg
        pass
    return "ffmpeg"


def preprocess_audio(
    media_path: Path,
    *,
    ffmpeg_cmd: Optional[str] = None,
    filter_chain: str = _DEFAULT_FILTER_CHAIN,
) -> Path:
    """Extract a cleaned 16 kHz mono WAV from ``media_path``.

    Returns the path to a freshly created temp WAV on success, or the original
    ``media_path`` unchanged when ffmpeg is unavailable or the conversion fails.
    Callers should pass the result straight to the transcriber and then call
    :func:`cleanup_temp_audio` to remove the temp file if one was created.
    """

    source = Path(media_path)
    if not source.exists():
        return source

    ffmpeg = (ffmpeg_cmd or "").strip() or _resolve_ffmpeg()

    fd, tmp_name = tempfile.mkstemp(prefix="asr_clean_", suffix=".wav")
    os.close(fd)
    tmp_path = Path(tmp_name)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vn",  # drop any video stream
        "-af",
        filter_chain,
        "-ar",
        _TARGET_SAMPLE_RATE,
        "-ac",
        "1",
        str(tmp_path),
    ]

    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("[asr.audio_preprocess] ffmpeg 调用失败，使用原始音轨: %s", exc)
        cleanup_temp_audio(tmp_path)
        return source

    if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size <= 0:
        logging.warning(
            "[asr.audio_preprocess] 音频预处理失败(rc=%s)，使用原始音轨: %s",
            result.returncode,
            (result.stderr or "").strip()[-240:],
        )
        cleanup_temp_audio(tmp_path)
        return source

    logging.info("[asr.audio_preprocess] 已生成降噪/归一化音轨: %s", tmp_path)
    return tmp_path


def cleanup_temp_audio(path: Optional[Path]) -> None:
    """Remove a temp WAV created by :func:`preprocess_audio` (best-effort)."""

    if path is None:
        return
    try:
        p = Path(path)
        # Only delete files we created (our temp prefix), never the source media.
        if p.exists() and p.name.startswith("asr_clean_"):
            p.unlink()
    except OSError:  # pragma: no cover - defensive
        logging.debug("[asr.audio_preprocess] 临时音频清理失败: %s", path)


__all__ = ["preprocess_audio", "cleanup_temp_audio"]
