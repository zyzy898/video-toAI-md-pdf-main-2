"""Speech-to-text (ASR) layer.

The project standardises on ``faster-whisper`` as the only ASR backend. The
``TranscriberBackend`` interface remains an abstraction so the rest of the
code never depends on the engine directly, but :func:`build_transcriber`
always returns a configured ``FasterWhisperBackend``.
"""

from .base import (
    SubtitleSegment,
    TranscribeResult,
    TranscriberBackend,
    TranscriberInitError,
    TranscriberNotAvailable,
)
from .srt_writer import write_srt_file
from .factory import build_transcriber

__all__ = [
    "SubtitleSegment",
    "TranscribeResult",
    "TranscriberBackend",
    "TranscriberInitError",
    "TranscriberNotAvailable",
    "write_srt_file",
    "build_transcriber",
]
