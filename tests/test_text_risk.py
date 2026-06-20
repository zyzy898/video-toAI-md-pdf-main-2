"""Tests for text-risk keyword gate (services/text_risk.py)."""

import pytest

from services.text_risk import (
    _build_text_fallback_risk_result,
    _count_keyword_hits,
    _normalize_risk_keyword_text,
    _normalize_text_risk_keyword_lexicon,
    _normalize_text_risk_keyword_list,
    _normalize_text_risk_reason_code,
    _default_text_risk_keyword_lexicon,
)


class TestNormalizeKeywordText:
    def test_lowercases_and_collapses(self):
        assert _normalize_risk_keyword_text("Hello   WORLD") == "hello world"

    def test_strips_punctuation(self):
        out = _normalize_risk_keyword_text("a!!!b???c")
        assert out == "a b c"

    def test_keeps_cjk(self):
        assert "测试" in _normalize_risk_keyword_text("测试 text")


class TestCountKeywordHits:
    def test_counts_explicit_and_medium(self):
        e, m, hits = _count_keyword_hits("the cat and dog", ["cat"], ["dog"])
        assert e == 1
        assert m == 1
        assert "cat" in hits and "dog" in hits

    def test_no_hits(self):
        e, m, hits = _count_keyword_hits("nothing here", ["xyz"], ["abc"])
        assert e == 0 and m == 0 and hits == []

    def test_caps_hit_keywords_at_6(self):
        explicit = [f"k{i}" for i in range(10)]
        text = " ".join(explicit)
        e, m, hits = _count_keyword_hits(text, explicit, [])
        assert e == 10
        assert len(hits) <= 6


class TestNormalizeKeywordList:
    def test_dedupes_and_lowercases(self):
        assert _normalize_text_risk_keyword_list(["A", "a", "B"]) == ["a", "b"]

    def test_non_list_returns_empty(self):
        assert _normalize_text_risk_keyword_list("nope") == []


class TestNormalizeReasonCode:
    def test_uppercases_and_sanitizes(self):
        assert _normalize_text_risk_reason_code("bad code!", "FALLBACK") == "BAD_CODE"

    def test_empty_uses_fallback(self):
        assert _normalize_text_risk_reason_code("", "FALLBACK") == "FALLBACK"


class TestNormalizeLexicon:
    def test_fills_all_dimensions(self):
        defaults = _default_text_risk_keyword_lexicon()
        out = _normalize_text_risk_keyword_lexicon({}, defaults)
        assert set(out.keys()) == {"nudity", "violence", "gore"}
        for dim in out.values():
            assert "explicit" in dim and "medium" in dim

    def test_merges_source_keywords(self):
        defaults = _default_text_risk_keyword_lexicon()
        out = _normalize_text_risk_keyword_lexicon(
            {"nudity": {"explicit": ["xxx"]}}, defaults
        )
        assert "xxx" in out["nudity"]["explicit"]


class TestBuildTextFallbackResult:
    def _lexicon_with(self, monkeypatch, explicit):
        import services.text_risk as tr
        lex = tr._default_text_risk_keyword_lexicon()
        lex["nudity"]["explicit"] = explicit
        monkeypatch.setattr(tr, "_load_text_risk_keyword_lexicon", lambda: lex)

    def test_clean_text_allows(self, monkeypatch):
        self._lexicon_with(monkeypatch, ["forbiddenword"])
        result = _build_text_fallback_risk_result("hello clean text", "hello clean text", "")
        assert result["decision"] == "allow"

    def test_explicit_hits_block(self, monkeypatch):
        # many explicit hits in both text + filename to push score over block threshold
        self._lexicon_with(monkeypatch, ["badword"])
        combined = "badword " * 5
        result = _build_text_fallback_risk_result(combined, combined, "badword")
        assert result["decision"] in ("block", "restrict")
        assert result["scores"]["nudity"] > 0
