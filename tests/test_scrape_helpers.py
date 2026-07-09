from services.scrape_helpers import (
    detect_human_verification_signals,
    parse_env_mapping,
)


def test_parse_env_mapping_accepts_json_object_and_discards_blank_values():
    assert parse_env_mapping('{"User-Agent": "UA", "empty": "", "spaces": "  value  "}') == {
        "User-Agent": "UA",
        "spaces": "value",
    }


def test_parse_env_mapping_accepts_semicolon_and_newline_key_value_pairs():
    assert parse_env_mapping("A=1; B = two\ninvalid\nC=3=tail") == {
        "A": "1",
        "B": "two",
        "C": "3=tail",
    }


def test_detect_human_verification_signals_deduplicates_and_limits_results():
    signals = detect_human_verification_signals(
        403,
        "https://example.com/security/captcha",
        "Cloudflare cf_challenge CAPTCHA \u8bf7\u5b8c\u6210\u9a8c\u8bc1 security check turnstile",
    )

    assert signals == [
        "http_403",
        "url_challenge_hint",
        "captcha",
        "turnstile",
        "cf_challenge",
        "human_check_en",
        "human_check_zh",
    ]


def test_detect_human_verification_signals_ignores_normal_pages():
    assert detect_human_verification_signals(200, "https://example.com/video", "normal page") == []
