"""faster-whisper backend.

Significantly faster and more memory-efficient than OpenAI's reference
implementation thanks to CTranslate2. This is the project's only ASR backend
and the dependency is required (see ``requirements.txt``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Optional

from .audio_preprocess import cleanup_temp_audio, preprocess_audio
from .base import (
    SubtitleSegment,
    TranscribeResult,
    TranscriberBackend,
    TranscriberError,
    TranscriberInitError,
    TranscriberNotAvailable,
)
from .zh_simplify import to_simplified


try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:  # pragma: no cover - exercised only when not installed
    WhisperModel = None  # type: ignore[assignment]


_DEFAULT_DEVICE = "auto"
_DEFAULT_COMPUTE_TYPE = "int8"


class FasterWhisperBackend(TranscriberBackend):
    """Backend powered by ``faster-whisper`` (CTranslate2)."""

    name = "faster_whisper"

    _model_cache: Dict[str, Any] = {}
    _model_cache_lock: RLock = RLock()
    _infer_lock: RLock = RLock()

    def __init__(
        self,
        *,
        model_size: str = "base",
        threads: Optional[int] = None,
        language: str = "zh",
        device: str = _DEFAULT_DEVICE,
        compute_type: str = _DEFAULT_COMPUTE_TYPE,
        beam_size: int = 5,
        vad_filter: bool = True,
        best_of: int = 5,
        condition_on_previous_text: bool = False,
        compression_ratio_threshold: float = 2.4,
        no_speech_threshold: float = 0.6,
        temperatures: Optional[tuple[float, ...]] = None,
        initial_prompt: Optional[str] = None,
        hotwords: Optional[str] = None,
        hotwords_provider: Optional[Callable[[], Optional[str]]] = None,
        preprocess_audio_enabled: bool = False,
        ffmpeg_cmd: Optional[str] = None,
    ) -> None:
        if WhisperModel is None:
            raise TranscriberNotAvailable(
                "faster-whisper 未安装。请运行 'pip install faster-whisper' 后重试。"
            )
        self.model_size = (model_size or "base").strip().lower() or "base"
        self.threads = max(1, min(16, int(threads or 1)))
        self.language = language or "zh"
        self.device = (device or _DEFAULT_DEVICE).strip().lower()
        self.compute_type = (compute_type or _DEFAULT_COMPUTE_TYPE).strip().lower()
        self.beam_size = max(1, min(10, int(beam_size or 1)))
        self.vad_filter = bool(vad_filter)
        # Quality-tuning knobs (sensible defaults that improve accuracy and
        # suppress the long-silence hallucinations Whisper is prone to).
        self.best_of = max(1, min(10, int(best_of or 1)))
        # Disabling cross-segment conditioning is the single most effective
        # guard against repeated/looping hallucinated captions.
        self.condition_on_previous_text = bool(condition_on_previous_text)
        self.compression_ratio_threshold = float(compression_ratio_threshold)
        self.no_speech_threshold = float(no_speech_threshold)
        # Temperature fallback ladder: greedy first, then progressively higher
        # so a failed/low-confidence decode is retried instead of kept.
        self.temperatures = tuple(temperatures) if temperatures else (0.0, 0.2, 0.4)
        # Plan A: bias decoding toward correct domain vocabulary. ``hotwords``
        # is the dedicated faster-whisper biasing arg; ``initial_prompt`` seeds
        # the decoder context. Both fight near-homophone errors at the source.
        self.initial_prompt = (str(initial_prompt).strip() or None) if initial_prompt else None
        # Static env-provided hotwords (the fixed base).
        self.hotwords = (str(hotwords).strip() or None) if hotwords else None
        # Optional callable re-invoked on EVERY transcribe() to pull the latest
        # self-learned glossary, so corrections made on earlier videos take
        # effect immediately on the next video without restarting the process.
        self._hotwords_provider = hotwords_provider
        # Plan B: clean the audio (denoise + loudness-normalise) before ASR.
        self.preprocess_audio_enabled = bool(preprocess_audio_enabled)
        self.ffmpeg_cmd = (str(ffmpeg_cmd).strip() or None) if ffmpeg_cmd else None

    def _effective_hotwords(self) -> Optional[str]:
        """Merge static env hotwords with the freshly re-read learned glossary.

        Called per transcription so the latest accumulated terms are always
        applied. The provider is best-effort: any failure falls back to the
        static base so transcription is never blocked.
        """

        parts = []
        if self.hotwords:
            parts.append(self.hotwords)
        if self._hotwords_provider is not None:
            try:
                learned = self._hotwords_provider()
            except Exception:  # pragma: no cover - never block on provider
                learned = None
            if learned and str(learned).strip():
                parts.append(str(learned).strip())
        # De-duplicate while preserving order (space-separated token merge).
        seen: set[str] = set()
        tokens: list[str] = []
        for chunk in parts:
            for tok in chunk.split():
                if tok and tok not in seen:
                    seen.add(tok)
                    tokens.append(tok)
        return " ".join(tokens) or None

    def cache_signature(self) -> str:
        # ``zhcn`` marks Simplified-Chinese normalised output; bumping it
        # invalidates older cached subtitles that may still be Traditional.
        # Decoding-quality knobs are part of the key so changing them does not
        # silently reuse subtitles produced with the old settings.
        prompt_tag = "p1" if self.initial_prompt else "p0"
        hot_tag = "h1" if self.hotwords else "h0"
        pre_tag = "a1" if self.preprocess_audio_enabled else "a0"
        return (
            f"{self.name}:{self.model_size}:{self.compute_type}:{self.beam_size}:"
            f"{self.best_of}:{int(self.condition_on_previous_text)}:"
            f"{self.compression_ratio_threshold:g}:{self.no_speech_threshold:g}:"
            f"{prompt_tag}:{hot_tag}:{pre_tag}:{int(self.vad_filter)}:zhcn"
        )

    def _model_cache_key(self) -> str:
        return f"{self.model_size}|{self.device}|{self.compute_type}|{self.threads}"

    def _get_model(self):
        cache_key = self._model_cache_key()
        with self._model_cache_lock:
            cached = self._model_cache.get(cache_key)
            if cached is not None:
                return cached
            try:
                model = WhisperModel(  # type: ignore[misc]
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    cpu_threads=self.threads,
                )
            except Exception as exc:
                raise TranscriberInitError(
                    f"faster-whisper 初始化失败: {exc}"
                ) from exc
            self._model_cache[cache_key] = model
            logging.info(
                "faster-whisper 模型已加载: %s (device=%s, compute=%s, threads=%s)",
                self.model_size,
                self.device,
                self.compute_type,
                self.threads,
            )
            return model

    def transcribe(self, video_path: Path, *, language: str = "zh") -> TranscribeResult:
        video_path = Path(video_path)
        if not video_path.exists():
            raise TranscriberError(f"视频文件不存在: {video_path}")
        lang = language or self.language
        normalize_zh = str(lang).lower().startswith("zh")

        model = self._get_model()
        # Plan B: optionally denoise + loudness-normalise the audio first. On
        # failure ``preprocess_audio`` returns the original path, so this never
        # blocks transcription. We track whether a temp file was made for cleanup.
        decode_path = video_path
        temp_audio: Optional[Path] = None
        if self.preprocess_audio_enabled:
            cleaned = preprocess_audio(video_path, ffmpeg_cmd=self.ffmpeg_cmd)
            if cleaned != video_path:
                decode_path = cleaned
                temp_audio = cleaned

        with self._infer_lock:
            try:
                transcribe_kwargs: Dict[str, Any] = {
                    "language": lang,
                    "beam_size": self.beam_size,
                    "vad_filter": self.vad_filter,
                    "best_of": self.best_of,
                    "temperature": list(self.temperatures),
                    "condition_on_previous_text": self.condition_on_previous_text,
                    "compression_ratio_threshold": self.compression_ratio_threshold,
                    "no_speech_threshold": self.no_speech_threshold,
                }
                if self.initial_prompt:
                    transcribe_kwargs["initial_prompt"] = self.initial_prompt
                effective_hotwords = self._effective_hotwords()
                if effective_hotwords:
                    transcribe_kwargs["hotwords"] = effective_hotwords
                segments_iter, info = model.transcribe(
                    str(decode_path),
                    **transcribe_kwargs,
                )
            except Exception as exc:
                cleanup_temp_audio(temp_audio)
                raise TranscriberError(f"faster-whisper 推理失败: {exc}") from exc
            segments = []
            try:
                for raw in segments_iter:
                    text = str(getattr(raw, "text", "") or "").strip()
                    if not text:
                        continue
                    if normalize_zh:
                        text = to_simplified(text)
                    try:
                        start = float(getattr(raw, "start", 0.0) or 0.0)
                        end = float(getattr(raw, "end", start) or start)
                    except (TypeError, ValueError):
                        continue
                    segments.append(SubtitleSegment(start=start, end=end, text=text))
            finally:
                cleanup_temp_audio(temp_audio)

        if not segments:
            raise TranscriberError("faster-whisper 未识别到任何字幕段")

        return TranscribeResult(
            segments=segments,
            language=str(getattr(info, "language", lang) or lang),
            duration=float(getattr(info, "duration", 0.0) or 0.0) or None,
            meta={
                "backend": self.name,
                "model": self.model_size,
                "device": self.device,
                "compute_type": self.compute_type,
                "beam_size": self.beam_size,
                "best_of": self.best_of,
                "condition_on_previous_text": self.condition_on_previous_text,
                "vad_filter": self.vad_filter,
                "initial_prompt_used": bool(self.initial_prompt),
                "hotwords_used": bool(effective_hotwords),
                "audio_preprocessed": temp_audio is not None,
            },
        )


__all__ = ["FasterWhisperBackend"]
