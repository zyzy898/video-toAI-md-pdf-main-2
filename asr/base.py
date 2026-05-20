"""Abstract transcriber backend interface and shared types.

The agent depends only on ``TranscriberBackend``; concrete implementations
(OpenAI Whisper, faster-whisper, ...) live in sibling modules. Each backend
returns segments shaped consistently so a shared SRT writer can format them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class TranscriberError(RuntimeError):
    """Generic transcription failure (engine specific)."""


class TranscriberInitError(TranscriberError):
    """Raised when a backend cannot be constructed (missing dependency, ...)."""


class TranscriberNotAvailable(TranscriberInitError):
    """Specialisation of init error: backend Python package is not installed."""


@dataclass
class SubtitleSegment:
    """A single transcribed segment with start/end seconds and text."""

    start: float
    end: float
    text: str


@dataclass
class TranscribeResult:
    """Container returned by :class:`TranscriberBackend`.

    Attributes:
        segments: ordered list of subtitle segments (seconds-based).
        language: language code that the engine actually used.
        duration: clip duration in seconds, when known. ``None`` otherwise.
        meta: free-form per-backend metadata for diagnostics / logging.
    """

    segments: List[SubtitleSegment]
    language: str = "zh"
    duration: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class TranscriberBackend(ABC):
    """Tiny stable interface the agent talks to."""

    #: Stable backend identifier ("faster_whisper").
    name: str = "unknown"

    #: Whisper-style model size ("tiny" / "base" / "small" / ...).
    model_size: str = "base"

    @abstractmethod
    def transcribe(
        self,
        video_path: Path,
        *,
        language: str = "zh",
    ) -> TranscribeResult:
        """Run speech-to-text and return :class:`TranscribeResult`.

        Implementations may use any engine but must:
          * raise :class:`TranscriberError` on hard failure (no partial state),
          * return at least one segment when speech is present,
          * be safe to call concurrently by holding their own locks if needed.
        """

    def cache_signature(self) -> str:
        """A short identifier mixed into the subtitle cache key.

        Even though the project currently ships a single backend, the cache key
        keeps the backend name + tuning parameters so future swaps (or simply
        changing ``WHISPER_COMPUTE_TYPE``) won't reuse stale subtitle files.
        """

        return f"{self.name}:{self.model_size}"

    def close(self) -> None:  # pragma: no cover - default no-op
        return None
