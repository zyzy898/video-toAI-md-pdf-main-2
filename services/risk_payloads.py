from __future__ import annotations

from typing import Any, Dict

_BUILTIN_BLOCK_REASON = "\u5185\u5bb9\u98ce\u9669\u8f83\u9ad8\uff0c\u5df2\u62e6\u622a\u5904\u7406\u3002"


def build_blocked_notice_payload(
    risk: Dict[str, Any],
    *,
    default_reason: str = "",
) -> Dict[str, Any]:
    risk_level = str(risk.get("risk_level", "high")).strip().lower() or "high"
    reason_code = str(risk.get("reason_code", "CONTENT_POLICY_VIOLATION")).strip().upper()
    reason = (
        str(risk.get("reason", "")).strip()
        or str(default_reason or "").strip()
        or _BUILTIN_BLOCK_REASON
    )
    return {
        "title": "\u5b89\u5168\u68c0\u6d4b\u672a\u901a\u8fc7\uff08\u5df2\u62e6\u622a\uff09",
        "risk_level": risk_level,
        "reason_code": reason_code,
        "reason": reason,
        "suggestions": [
            "\u5220\u9664\u6216\u66ff\u6362\u6d89\u53ca\u8272\u60c5/\u88f8\u9732/\u8840\u8165/\u66b4\u529b\u7684\u654f\u611f\u753b\u9762\u3002",
            "\u5bf9\u9ad8\u98ce\u9669\u7247\u6bb5\u8fdb\u884c\u88c1\u526a\u3001\u6253\u7801\u6216\u5f31\u5316\u5904\u7406\u540e\u518d\u5bfc\u51fa\u89c6\u9891\u3002",
            "\u5b8c\u6210\u6574\u6539\u540e\u91cd\u65b0\u4e0a\u4f20\u5e76\u53d1\u8d77\u5b89\u5168\u68c0\u6d4b\u3002",
        ],
        "retry_guidance": "\u8bf7\u5148\u5b8c\u6210\u5185\u5bb9\u6574\u6539\uff0c\u518d\u91cd\u65b0\u4e0a\u4f20\u89e6\u53d1\u68c0\u6d4b\u3002",
    }
