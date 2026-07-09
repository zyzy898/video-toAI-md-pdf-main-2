from services.risk_payloads import build_blocked_notice_payload


BLOCK_TITLE = "\u5b89\u5168\u68c0\u6d4b\u672a\u901a\u8fc7\uff08\u5df2\u62e6\u622a\uff09"
DEFAULT_REASON = "\u9ed8\u8ba4\u62e6\u622a\u539f\u56e0"


def test_build_blocked_notice_payload_normalizes_risk_fields():
    payload = build_blocked_notice_payload(
        {
            "risk_level": " HIGH ",
            "reason_code": " unsafe_content ",
            "reason": "  matched policy  ",
        },
        default_reason=DEFAULT_REASON,
    )

    assert payload["title"] == BLOCK_TITLE
    assert payload["risk_level"] == "high"
    assert payload["reason_code"] == "UNSAFE_CONTENT"
    assert payload["reason"] == "matched policy"
    assert len(payload["suggestions"]) == 3
    assert payload["retry_guidance"]


def test_build_blocked_notice_payload_uses_safe_defaults():
    payload = build_blocked_notice_payload({}, default_reason=DEFAULT_REASON)

    assert payload["risk_level"] == "high"
    assert payload["reason_code"] == "CONTENT_POLICY_VIOLATION"
    assert payload["reason"] == DEFAULT_REASON


def test_build_blocked_notice_payload_falls_back_to_builtin_reason():
    payload = build_blocked_notice_payload({"reason": "   "}, default_reason="")

    assert payload["reason"] == "\u5185\u5bb9\u98ce\u9669\u8f83\u9ad8\uff0c\u5df2\u62e6\u622a\u5904\u7406\u3002"
