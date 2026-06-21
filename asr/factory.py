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


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _env_str(name: str) -> Optional[str]:
    raw = str(os.getenv(name, "")).strip()
    return raw or None


def _env_temperatures(
    name: str, default: tuple[float, ...]
) -> tuple[float, ...]:
    """Parse a comma-separated temperature ladder, e.g. ``"0.0,0.2,0.4"``."""

    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    values: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(max(0.0, min(1.0, float(part))))
        except (TypeError, ValueError):
            continue
    return tuple(values) if values else default


def _learned_hotwords_provider() -> Optional[str]:
    """Re-read the self-learned glossary file on demand (called per transcribe).

    Kept as a callable - not a value - so corrections accumulated during the
    current process take effect on the very next video, with no restart.
    """

    try:
        from .correction_log import load_hotwords

        learned = load_hotwords()
        return learned or None
    except Exception:  # pragma: no cover - never block transcriber build
        return None


def build_transcriber(
    *,
    model_size: str = "base",
    threads: Optional[int] = None,
    language: str = "zh",
    ffmpeg_cmd: Optional[str] = None,
) -> TranscriberBackend:
    """Build a :class:`FasterWhisperBackend` from environment configuration.

    Args:
        model_size: whisper model identifier (``tiny``/``base``/``small``/...).
        threads: CPU thread count. ``None`` lets the backend pick.
        language: target language passed to the backend at decode time.
        ffmpeg_cmd: ffmpeg executable used for optional audio pre-processing
            (Plan B). ``None`` lets the backend discover one.
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
            # Default beam_size bumped 1 -> 5: greedy decoding wastes the
            # accuracy a large model can deliver. Still env-overridable.
            beam_size=_env_int("WHISPER_BEAM_SIZE", 5, lo=1, hi=10),
            vad_filter=_env_bool("WHISPER_VAD_FILTER", True),
            best_of=_env_int("WHISPER_BEST_OF", 5, lo=1, hi=10),
            # Off by default: the strongest guard against looping/repeated
            # hallucinated captions in long silent stretches.
            condition_on_previous_text=_env_bool(
                "WHISPER_CONDITION_ON_PREVIOUS_TEXT", False
            ),
            compression_ratio_threshold=_env_float(
                "WHISPER_COMPRESSION_RATIO_THRESHOLD", 2.4, lo=1.0, hi=10.0
            ),
            no_speech_threshold=_env_float(
                "WHISPER_NO_SPEECH_THRESHOLD", 0.6, lo=0.0, hi=1.0
            ),
            temperatures=_env_temperatures("WHISPER_TEMPERATURES", (0.0, 0.2, 0.4)),
            # Plan A: domain hot-words / glossary to bias proper-noun and
            # near-homophone recognition at decode time.
            initial_prompt=_env_str("WHISPER_INITIAL_PROMPT"),
            # Static env hotwords are the fixed base; the provider re-reads the
            # self-learned glossary on every transcribe() so fixes take effect
            # immediately on the next video (no process restart needed).
            hotwords=_env_str("WHISPER_HOTWORDS"),
            hotwords_provider=_learned_hotwords_provider,
            # Plan B: denoise + loudness-normalise audio before ASR.
            preprocess_audio_enabled=_env_bool("WHISPER_PREPROCESS_AUDIO", False),
            ffmpeg_cmd=ffmpeg_cmd,
        )
    except TranscriberNotAvailable:
        # The backend itself raises this when faster_whisper is missing.
        # Re-raise so the agent fails fast rather than silently degrading.
        logging.error(
            "[asr.factory] faster-whisper 未安装，请运行: pip install faster-whisper"
        )
        raise


__all__ = ["build_transcriber"]
