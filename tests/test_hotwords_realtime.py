"""Tests for FasterWhisperBackend.realtime hotwords merging (_effective_hotwords).

These bypass __init__ via object.__new__ to avoid the WhisperModel dependency;
only the attributes _effective_hotwords touches are injected.
"""

from asr.faster_whisper_backend import FasterWhisperBackend


def _make_backend(static, provider):
    b = FasterWhisperBackend.__new__(FasterWhisperBackend)
    b.hotwords = static
    b._hotwords_provider = provider
    return b


def test_merges_static_and_learned():
    b = _make_backend("点赞", lambda: "帖子 在线")
    assert b._effective_hotwords() == "点赞 帖子 在线"


def test_reflects_provider_changes_without_rebuild():
    state = {"v": "帖子"}
    b = _make_backend("点赞", lambda: state["v"])
    assert b._effective_hotwords() == "点赞 帖子"
    state["v"] = "帖子 在线 牛客网"  # glossary grows mid-process
    assert b._effective_hotwords() == "点赞 帖子 在线 牛客网"


def test_dedupes_overlap_preserving_order():
    b = _make_backend("点赞 帖子", lambda: "帖子 点赞 在线")
    assert b._effective_hotwords() == "点赞 帖子 在线"


def test_provider_failure_falls_back_to_static():
    def _boom():
        raise RuntimeError("provider down")

    b = _make_backend("点赞", _boom)
    assert b._effective_hotwords() == "点赞"


def test_no_hotwords_returns_none():
    b = _make_backend(None, lambda: None)
    assert b._effective_hotwords() is None


def test_only_learned_no_static():
    b = _make_backend(None, lambda: "帖子 在线")
    assert b._effective_hotwords() == "帖子 在线"
