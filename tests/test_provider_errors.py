from llm_client import Capability, ProviderFeatureUnsupportedError
from services.provider_errors import (
    as_bool,
    extract_http_status_code,
    extract_request_id,
    normalize_provider_error,
)


def test_as_bool_accepts_common_truthy_strings_only():
    assert as_bool(True) is True
    assert as_bool(" YES ") is True
    assert as_bool("on") is True
    assert as_bool("false") is False
    assert as_bool(0) is False


def test_extract_request_id_handles_separator_variants():
    assert extract_request_id("request_id: req-abc_123") == "req-abc_123"
    assert extract_request_id("Request-ID = 'req.456'") == "req.456"
    assert extract_request_id("no request id here") == ""


def test_extract_http_status_code_accepts_known_formats_and_rejects_invalid_codes():
    assert extract_http_status_code("status_code=429") == 429
    assert extract_http_status_code("HTTP 500 server error") == 500
    assert extract_http_status_code("{\"status\": 403}") == 403
    assert extract_http_status_code("status_code=999") is None


def test_normalize_provider_error_maps_common_provider_failures():
    message, status, handled = normalize_provider_error(
        "authentication_error: incorrect api key provided request_id: req-auth",
        web_search_activation_url="https://activate.example/",
    )

    assert status == 401
    assert handled is True
    assert "????" in message
    assert "req-auth" in message

    message, status, handled = normalize_provider_error(
        "rate limit exceeded request-id: req-rate",
        web_search_activation_url="https://activate.example/",
    )

    assert status == 429
    assert handled is True
    assert "req-rate" in message


def test_normalize_provider_error_maps_provider_feature_unsupported():
    err = ProviderFeatureUnsupportedError(
        provider="openai-compatible",
        capability=Capability.WEB_SEARCH_TOOL,
        hint="disable search",
    )

    message, status, handled = normalize_provider_error(
        err,
        web_search_activation_url="https://activate.example/",
    )

    assert status == 400
    assert handled is True
    assert "openai-compatible" in message
    assert "web_search_tool" in message
    assert "disable search" in message
    assert "code=provider_feature_unsupported" in message
