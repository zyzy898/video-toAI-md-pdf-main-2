"""Smoke tests for pure helper functions in app.py.

These pin down current behavior so structural refactors (module extraction)
can be verified without changing semantics. They intentionally avoid Flask
request context, network, and filesystem side effects.
"""

import pytest

import app


class TestEnvHelpers:
    def test_env_int_valid(self, monkeypatch):
        monkeypatch.setenv("SMOKE_ENV_INT", "42")
        assert app._env_int("SMOKE_ENV_INT", 0) == 42

    def test_env_int_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("SMOKE_ENV_INT", "not-a-number")
        assert app._env_int("SMOKE_ENV_INT", 7) == 7

    def test_env_int_missing_falls_back(self, monkeypatch):
        monkeypatch.delenv("SMOKE_ENV_INT", raising=False)
        assert app._env_int("SMOKE_ENV_INT", 9) == 9

    def test_env_text_first_present_wins(self, monkeypatch):
        monkeypatch.delenv("SMOKE_A", raising=False)
        monkeypatch.setenv("SMOKE_B", "second")
        assert app._env_text(("SMOKE_A", "SMOKE_B"), "default") == "second"

    def test_env_text_default(self, monkeypatch):
        monkeypatch.delenv("SMOKE_A", raising=False)
        monkeypatch.delenv("SMOKE_B", raising=False)
        assert app._env_text(("SMOKE_A", "SMOKE_B"), "default") == "default"

    @pytest.mark.parametrize(
        "raw,expected",
        [("1", True), ("true", True), ("YES", True), ("on", True),
         ("0", False), ("false", False), ("", True)],
    )
    def test_env_bool(self, monkeypatch, raw, expected):
        # empty string -> default (True here)
        if raw == "":
            monkeypatch.delenv("SMOKE_BOOL", raising=False)
            assert app._env_bool(("SMOKE_BOOL",), True) is True
        else:
            monkeypatch.setenv("SMOKE_BOOL", raw)
            assert app._env_bool(("SMOKE_BOOL",), False) is expected


class TestSafeNumeric:
    def test_safe_int_clamps_high(self):
        assert app._safe_int("7", 0, 1, 5) == 5

    def test_safe_int_clamps_low(self):
        assert app._safe_int("-3", 0, 1, 5) == 1

    def test_safe_int_invalid_default(self):
        assert app._safe_int("abc", 3) == 3

    def test_safe_float_invalid_default(self):
        assert app._safe_float("x", 1.5, 0.0, 2.0) == 1.5

    def test_safe_float_clamps(self):
        assert app._safe_float("9.0", 0.0, 0.0, 2.0) == 2.0


class TestRiskScoring:
    def test_normalize_risk_score_clamps_to_one(self):
        assert app._normalize_risk_score("2.0") == 1.0

    def test_normalize_risk_score_clamps_to_zero(self):
        assert app._normalize_risk_score("-1.0") == 0.0

    def test_normalize_risk_score_invalid(self):
        assert app._normalize_risk_score("oops", default=0.3) == 0.3

    @pytest.mark.parametrize(
        "decision,rank", [("allow", 0), ("restrict", 1), ("block", 2), ("unknown", 0)]
    )
    def test_decision_rank(self, decision, rank):
        assert app._risk_decision_rank(decision) == rank

    @pytest.mark.parametrize(
        "rank,decision", [(0, "allow"), (1, "restrict"), (2, "block"), (5, "block")]
    )
    def test_decision_from_rank(self, rank, decision):
        assert app._risk_decision_from_rank(rank) == decision

    @pytest.mark.parametrize(
        "decision,level",
        [("block", "high"), ("restrict", "medium"), ("allow", "low")],
    )
    def test_level_from_decision(self, decision, level):
        assert app._risk_level_from_decision(decision) == level


class TestFileHelpers:
    @pytest.mark.parametrize(
        "name,ok",
        [("a.mp4", True), ("a.MOV", True), ("a.txt", False), ("noext", False)],
    )
    def test_allowed_file(self, name, ok):
        assert app.allowed_file(name) is ok

    def test_safe_video_filename_strips_traversal(self):
        result = app._safe_video_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result and "\\" not in result

    def test_safe_video_filename_keeps_basename(self):
        assert app._safe_video_filename("clip.mp4") == "clip.mp4"


class TestUrlNormalization:
    def test_normalize_trims_whitespace(self):
        assert app._normalize_source_url("  https://example.com/v.mp4 ") == "https://example.com/v.mp4"

    def test_normalize_rejects_empty(self):
        with pytest.raises(ValueError):
            app._normalize_source_url("")

    def test_normalize_rejects_non_http_scheme(self):
        with pytest.raises(ValueError):
            app._normalize_source_url("ftp://example.com/v.mp4")


class TestSegmentZone:
    def test_standard_zone(self):
        from services.segment_policy import _classify_video_segment_zone
        assert _classify_video_segment_zone(60.0, 10.0) == "standard"

    def test_trim_required_for_oversized(self):
        from services.segment_policy import _classify_video_segment_zone
        assert _classify_video_segment_zone(99999.0, 9999.0) == "trim_required"


class TestSSRFGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/v.mp4",
            "http://192.168.1.1/",
            "http://0.0.0.0/",
        ],
    )
    def test_blocks_internal(self, url):
        with pytest.raises(ValueError):
            app._assert_url_not_internal(url)

    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValueError):
            app._assert_url_not_internal("ftp://example.com/x")

    def test_allows_public_host(self):
        # Should not raise for a resolvable public host.
        app._assert_url_not_internal("https://example.com/v.mp4")

    def test_respects_allow_flag(self, monkeypatch):
        monkeypatch.setattr(app, "URL_IMPORT_ALLOW_PRIVATE_HOSTS", True)
        # When explicitly allowed, internal hosts must pass.
        app._assert_url_not_internal("http://127.0.0.1/x")
