import ipaddress
import socket

import pytest

from services.url_safety import (
    assert_url_not_internal,
    is_disallowed_ip,
    looks_like_html_payload,
)


def _resolver_for(*ips: str):
    def _resolve(hostname, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (ip, port or 443)) for ip in ips]

    return _resolve


def test_is_disallowed_ip_rejects_private_loopback_and_reserved_ranges():
    assert is_disallowed_ip(ipaddress.ip_address("127.0.0.1")) is True
    assert is_disallowed_ip(ipaddress.ip_address("10.1.2.3")) is True
    assert is_disallowed_ip(ipaddress.ip_address("169.254.1.1")) is True
    assert is_disallowed_ip(ipaddress.ip_address("8.8.8.8")) is False


def test_assert_url_not_internal_rejects_literal_private_ip():
    with pytest.raises(ValueError, match="\u5185\u7f51\u6216\u4fdd\u7559\u5730\u5740"):
        assert_url_not_internal("http://127.0.0.1/video.mp4")


def test_assert_url_not_internal_can_allow_private_hosts_when_explicitly_enabled():
    assert_url_not_internal("http://127.0.0.1/video.mp4", allow_private_hosts=True)


def test_assert_url_not_internal_rejects_domains_resolving_to_private_ips():
    with pytest.raises(ValueError, match="\u5185\u7f51\u6216\u4fdd\u7559\u5730\u5740"):
        assert_url_not_internal(
            "https://example.com/video.mp4",
            getaddrinfo=_resolver_for("8.8.8.8", "10.0.0.2"),
        )


def test_assert_url_not_internal_accepts_public_dns_results():
    assert_url_not_internal(
        "https://example.com/video.mp4",
        getaddrinfo=_resolver_for("8.8.8.8"),
    )


def test_looks_like_html_payload_detects_html_or_xml_prefixes():
    assert looks_like_html_payload(b"  <!doctype html><html>") is True
    assert looks_like_html_payload(b"\n<html><body>not a video") is True
    assert looks_like_html_payload(b"<?xml version=\"1.0\"?><root>") is True
    assert looks_like_html_payload(b"\x00\x00\x00 ftypmp42") is False
