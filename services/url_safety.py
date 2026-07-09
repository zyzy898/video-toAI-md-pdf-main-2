"""URL safety helpers for remote video imports."""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlparse

AddressInfoResolver = Callable[..., list[tuple]]


def is_disallowed_ip(ip_obj: ipaddress._BaseAddress) -> bool:
    """Return True for private/reserved/local ranges that must not be fetched."""
    return bool(
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def assert_url_not_internal(
    raw_url: str,
    *,
    allow_private_hosts: bool = False,
    getaddrinfo: AddressInfoResolver = socket.getaddrinfo,
) -> None:
    """Reject URLs whose host is, or resolves to, private/reserved addresses."""
    if allow_private_hosts:
        return

    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("\u4ec5\u652f\u6301 http/https \u89c6\u9891\u94fe\u63a5")

    hostname = (parsed.hostname or "").strip()
    if not hostname:
        raise ValueError("\u65e0\u6cd5\u89e3\u6790\u94fe\u63a5\u4e3b\u673a\u540d")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if is_disallowed_ip(literal_ip):
            raise ValueError("\u51fa\u4e8e\u5b89\u5168\u8003\u8651\uff0c\u7981\u6b62\u8bbf\u95ee\u5185\u7f51\u6216\u4fdd\u7559\u5730\u5740")
        return

    try:
        addr_infos = getaddrinfo(hostname, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"\u65e0\u6cd5\u89e3\u6790\u94fe\u63a5\u4e3b\u673a\u540d\uff1a{hostname}") from exc

    resolved_ips = {info[4][0] for info in addr_infos if info and info[4]}
    if not resolved_ips:
        raise ValueError(f"\u65e0\u6cd5\u89e3\u6790\u94fe\u63a5\u4e3b\u673a\u540d\uff1a{hostname}")

    for ip_text in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if is_disallowed_ip(ip_obj):
            raise ValueError("\u51fa\u4e8e\u5b89\u5168\u8003\u8651\uff0c\u7981\u6b62\u8bbf\u95ee\u5185\u7f51\u6216\u4fdd\u7559\u5730\u5740")


def looks_like_html_payload(prefix: bytes) -> bool:
    """Heuristically detect text/html content even when headers are wrong."""
    snippet = bytes(prefix or b"").lstrip().lower()[:180]
    if not snippet:
        return False
    return (
        snippet.startswith(b"<!doctype html")
        or snippet.startswith(b"<html")
        or b"<html" in snippet
        or snippet.startswith(b"<?xml")
    )
