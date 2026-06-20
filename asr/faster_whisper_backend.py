"""faster-whisper backend.

Significantly faster and more memory-efficient than OpenAI's reference
implementation thanks to CTranslate2. This is the project's only ASR backend
and the dependency is required (see ``requirements.txt``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional

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
        beam_size: int = 1,
        vad_filter: bool = True,
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

    def cache_signature(self) -> str:
        # ``zhcn`` marks Simplified-Chinese normalised output; bumping it
        # invalidates older cached subtitles that may still be Traditional.
        return (
            f"{self.name}:{self.model_size}:{self.compute_type}:{self.beam_size}:"
            f"{int(self.vad_filter)}:zhcn"
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
        with self._infer_lock:
            try:
                segments_iter, info = model.transcribe(
                    str(video_path),
                    language=lang,
                    beam_size=self.beam_size,
                    vad_filter=self.vad_filter,
                )
            except Exception as exc:
                raise TranscriberError(f"faster-whisper 推理失败: {exc}") from exc
            segments = []
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
                "vad_filter": self.vad_filter,
            },
        )


__all__ = ["FasterWhisperBackend"]
