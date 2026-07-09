"""Normalize provider-side errors for user-facing API responses."""

from __future__ import annotations

import re
from typing import Any, Tuple

from llm_client import ProviderFeatureUnsupportedError


def as_bool(value: Any) -> bool:
    """Coerce form/query JSON values using the app's legacy truthy string rules."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def extract_request_id(message: str) -> str:
    """Extract a provider request id from free-form error text."""
    match = re.search(
        r"request[_\s-]*id['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9._-]+)",
        str(message or ""),
        flags=re.IGNORECASE,
    )
    return str(match.group(1)).strip() if match else ""


def extract_http_status_code(message: str) -> int | None:
    """Extract a valid HTTP status code from common provider error formats."""
    text = str(message or "")
    patterns = (
        r"(?:error[_\s]*code|status[_\s]*code|http(?:[_\s]*status)?)\s*[:=]?\s*(\d{3})",
        r"['\"]status['\"]\s*[:=]\s*(\d{3})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            status_code = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if 100 <= status_code <= 599:
            return status_code
    return None


def normalize_provider_error(
    error: Any,
    default_status: int = 500,
    *,
    web_search_activation_url: str = "",
) -> Tuple[str, int, bool]:
    """Return ``(message, http_status, handled)`` for provider exceptions/text."""
    if isinstance(error, ProviderFeatureUnsupportedError):
        capability = getattr(error.capability, "value", str(error.capability))
        hint = f" {error.hint}" if error.hint else ""
        return (
            f"?????? {error.provider} ????? {capability}?"
            f"????????????????{hint} | code=provider_feature_unsupported",
            400,
            True,
        )

    raw_message = str(error or "").strip() or "????????"
    lower = raw_message.lower()
    request_id = extract_request_id(raw_message)
    request_id_text = f"??? ID?{request_id}?" if request_id else ""

    is_web_search_not_open = (
        "toolnotopen" in lower or "web search" in lower or "????" in raw_message
    )
    if is_web_search_not_open:
        return (
            f"??????????????????{web_search_activation_url}{request_id_text}",
            400,
            True,
        )

    is_auth_error = (
        "authentication fails" in lower
        or "authentication_error" in lower
        or "invalid_api_key" in lower
        or "incorrect api key provided" in lower
        or "api key format is incorrect" in lower
        or ("api key" in lower and ("invalid" in lower or "is invalid" in lower or "??" in raw_message))
    )
    if is_auth_error:
        return (
            f"???????API Key ?????????????/Base URL ????{request_id_text}",
            401,
            True,
        )

    if "invalidendpointormodel.notfound" in lower or (
        "model or endpoint" in lower and "not found" in lower
    ):
        return (
            f"??????????????????? Base URL ??????{request_id_text}",
            400,
            True,
        )

    if "does not exist or you do not have access" in lower:
        return (
            f"???????????????????????{request_id_text}",
            403,
            True,
        )

    if "rate limit" in lower or "too many requests" in lower:
        return (f"?????????????{request_id_text}", 429, True)

    if "timeout" in lower or "timed out" in lower:
        return (f"???????????????{request_id_text}", 504, True)

    status_code = extract_http_status_code(raw_message)
    if status_code is not None and 400 <= status_code <= 599:
        return (f"?????????HTTP {status_code}??{request_id_text}", status_code, True)

    return raw_message, default_status, False
