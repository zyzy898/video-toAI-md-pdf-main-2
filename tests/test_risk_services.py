"""Tests for risk-related services extracted from app.py."""

import logging
from threading import RLock

import pytest

from services.risk_blocklist import RiskBlocklistService
from services.risk_cache import RiskResultCacheService


@pytest.fixture
def blocklist(tmp_path):
    return RiskBlocklistService(
        blocklist_path=tmp_path / "blocklist.json",
        lock_obj=RLock(),
        logger_obj=logging.getLogger("test.blocklist"),
    )


@pytest.fixture
def cache(tmp_path):
    return RiskResultCacheService(
        cache_path=tmp_path / "cache.json",
        lock_obj=RLock(),
        ttl_seconds=3600,
        max_entries=50,
        logger_obj=logging.getLogger("test.cache"),
    )


class TestBlocklistNormalization:
    def test_valid_64_hex(self, blocklist):
        assert blocklist.normalize_sha256_fingerprint("A" * 64) == "a" * 64

    def test_strips_non_hex(self, blocklist):
        # 64 hex chars with separators interspersed
        raw = ":".join(["ab"] * 32)  # 64 hex + colons
        assert blocklist.normalize_sha256_fingerprint(raw) == "ab" * 32

    def test_rejects_wrong_length(self, blocklist):
        assert blocklist.normalize_sha256_fingerprint("abc") == ""


class TestBlocklistRegisterMatch:
    def test_register_then_match(self, blocklist):
        fp = "a" * 64
        blocklist.register_blocked_fingerprint(
            fp, {"reason_code": "X", "reason": "bad", "decision": "block"}, "test"
        )
        risk = blocklist.match_fingerprint(fp, "another-source")
        assert risk is not None
        assert risk["decision"] == "block"
        assert risk["hash_sha256"] == fp

    def test_match_unknown_returns_none(self, blocklist):
        assert blocklist.match_fingerprint("b" * 64, "src") is None

    def test_register_increments_block_count(self, blocklist):
        fp = "c" * 64
        blocklist.register_blocked_fingerprint(fp, {"reason": "r"}, "s1")
        blocklist.register_blocked_fingerprint(fp, {"reason": "r"}, "s2")
        entries = blocklist.load_unlocked()
        assert entries[fp]["block_count"] == 2


class TestCacheModelKey:
    def test_model_key_ignores_trailing_slash(self, cache):
        assert cache.build_model_key("m", "https://h/") == cache.build_model_key("m", "https://h")

    def test_model_key_case_insensitive(self, cache):
        assert cache.build_model_key("M", "https://H") == cache.build_model_key("m", "https://h")

    def test_cache_key_requires_valid_inputs(self, cache):
        assert cache.build_cache_key("", "x") == ""
        assert cache.build_cache_key("a" * 64, "") == ""


class TestCacheGetSet:
    def test_set_then_get(self, cache):
        fp = "d" * 64
        mk = cache.build_model_key("m", "https://h")
        cache.set(fp, mk, {"decision": "allow", "confidence": 0.1})
        got = cache.get(fp, mk)
        assert got is not None
        assert got["decision"] == "allow"

    def test_get_missing_returns_none(self, cache):
        mk = cache.build_model_key("m", "https://h")
        assert cache.get("e" * 64, mk) is None

    def test_set_empty_risk_is_noop(self, cache):
        fp = "f" * 64
        mk = cache.build_model_key("m", "https://h")
        cache.set(fp, mk, {})
        assert cache.get(fp, mk) is None
