"""Traditional → Simplified Chinese normalisation.

Whisper (and faster-whisper) frequently emit Traditional Chinese characters
for Mandarin audio because of its training data mix. The rest of this project
expects Simplified Chinese, so transcribed text is normalised here.

Uses ``zhconv`` (pure-Python, no native dependency). If the package is missing
the text is returned unchanged so transcription never hard-fails over this.
"""

from __future__ import annotations

import logging

try:
    from zhconv import convert as _zh_convert  # type: ignore
except Exception:  # pragma: no cover - exercised only when not installed
    _zh_convert = None  # type: ignore[assignment]

_warned = False


def to_simplified(text: str) -> str:
    """Convert Traditional Chinese in ``text`` to Simplified Chinese.

    Returns the input unchanged when it is empty or when ``zhconv`` is not
    installed (a warning is logged once).
    """

    global _warned
    if not text:
        return text
    if _zh_convert is None:
        if not _warned:
            logging.warning(
                "[asr.zh_simplify] zhconv 未安装，跳过繁简转换。"
                "请运行 'pip install zhconv' 以输出简体中文。"
            )
            _warned = True
        return text
    try:
        return _zh_convert(text, "zh-cn")
    except Exception:  # pragma: no cover - defensive, never block transcription
        logging.exception("[asr.zh_simplify] 繁简转换失败，返回原文")
        return text


__all__ = ["to_simplified"]
