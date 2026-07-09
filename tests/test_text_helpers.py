from services.text_helpers import compact_text


def test_compact_text_collapses_whitespace_and_strips_edges():
    assert compact_text("  hello\n\t world  ", limit=50) == "hello world"


def test_compact_text_truncates_with_ellipsis_within_limit():
    assert compact_text("abcdef", limit=4) == "abc\u2026"


def test_compact_text_uses_minimum_limit_of_one():
    assert compact_text("abcdef", limit=0) == "a\u2026"


def test_compact_text_treats_none_as_empty_text():
    assert compact_text(None, limit=10) == ""
