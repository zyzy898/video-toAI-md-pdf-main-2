"""Build the project's transcriber backend.

The project standardises on ``faster-whisper`` (CTranslate2). There is no
runtime backend switch: the dependency is mandatory and the agent calls
``build_transcriber`` to obtain a single, well-configured instance.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .base import TranscriberBackend, TranscriberInitError, TranscriberNotAvailable


def _env_int(name: str, default: int, *, lo: int = 1, hi: int = 16) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def build_transcriber(
    *,
    model_size: str = "base",
    threads: Optional[int] = None,
    language: str = "zh",
) -> TranscriberBackend:
    """Build a :class:`FasterWhisperBackend` from environment configuration.

    Args:
        model_size: whisper model identifier (``tiny``/``base``/``small``/...).
        threads: CPU thread count. ``None`` lets the backend pick.
        language: target language passed to the backend at decode time.
    """

    try:
        from .faster_whisper_backend import FasterWhisperBackend
    except Exception as exc:  # pragma: no cover - import failure is fatal
        raise TranscriberInitError(
            "faster-whisper 不可用：导入失败，请确保已安装 'faster-whisper'。"
        ) from exc

    try:
        return FasterWhisperBackend(
            model_size=model_size,
            threads=threads,
            language=language,
            device=str(os.getenv("WHISPER_DEVICE", "auto")).strip() or "auto",
            compute_type=str(os.getenv("WHISPER_COMPUTE_TYPE", "int8")).strip()
            or "int8",
            beam_size=_env_int("WHISPER_BEAM_SIZE", 1, lo=1, hi=10),
            vad_filter=_env_bool("WHISPER_VAD_FILTER", True),
        )
    except TranscriberNotAvailable:
        # The backend itself raises this when faster_whisper is missing.
        # Re-raise so the agent fails fast rather than silently degrading.
        logging.error(
            "[asr.factory] faster-whisper 未安装，请运行: pip install faster-whisper"
        )
        raise


__all__ = ["build_transcriber"]
