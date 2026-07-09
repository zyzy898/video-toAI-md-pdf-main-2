import pytest

from utils import (
    _is_image_input_not_supported_error,
    _normalize_risk_score,
    _risk_decision_from_rank,
    _risk_decision_rank,
    _risk_level_from_decision,
    _safe_float,
    _safe_int,
)


def test_safe_int_clamps_and_defaults():
    assert _safe_int("7", 0, 1, 5) == 5
    assert _safe_int("-3", 0, 1, 5) == 1
    assert _safe_int("abc", 3) == 3


def test_safe_float_clamps_and_defaults():
    assert _safe_float("9.0", 0.0, 0.0, 2.0) == 2.0
    assert _safe_float("x", 1.5, 0.0, 2.0) == 1.5


def test_normalize_risk_score_clamps_and_defaults():
    assert _normalize_risk_score("2.0") == 1.0
    assert _normalize_risk_score("-1.0") == 0.0
    assert _normalize_risk_score("oops", default=0.3) == 0.3


@pytest.mark.parametrize(
    ("decision", "rank"),
    [("allow", 0), ("restrict", 1), ("block", 2), ("unknown", 0), (None, 0)],
)
def test_risk_decision_rank(decision, rank):
    assert _risk_decision_rank(decision) == rank


@pytest.mark.parametrize(
    ("rank", "decision"),
    [(-1, "allow"), (0, "allow"), (1, "restrict"), (2, "block"), (5, "block")],
)
def test_risk_decision_from_rank(rank, decision):
    assert _risk_decision_from_rank(rank) == decision


@pytest.mark.parametrize(
    ("decision", "level"),
    [("block", "high"), ("restrict", "medium"), ("allow", "low"), ("unknown", "low")],
)
def test_risk_level_from_decision(decision, level):
    assert _risk_level_from_decision(decision) == level



def test_detects_image_input_not_supported_errors():
    assert _is_image_input_not_supported_error(
        "This model does not support image_url content"
    )
    assert _is_image_input_not_supported_error(
        "Vision input is unsupported by the selected provider"
    )


def test_ignores_unrelated_or_supported_image_errors():
    assert not _is_image_input_not_supported_error("")
    assert not _is_image_input_not_supported_error(None)
    assert not _is_image_input_not_supported_error("temporary network timeout")
    assert not _is_image_input_not_supported_error("image_url request accepted")
    assert not _is_image_input_not_supported_error("unsupported text-only option")
