"""Helpers for building yt-dlp cookie source options."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

SUPPORTED_YTDLP_COOKIE_BROWSERS = {
    "chrome",
    "edge",
    "firefox",
    "safari",
    "opera",
    "brave",
    "chromium",
    "vivaldi",
    "whale",
}


def parse_csv_text(raw_value: Any) -> List[str]:
    """Split comma/semicolon/newline separated text while preserving first-seen order."""
    text = str(raw_value or "").strip()
    if not text:
        return []
    items: List[str] = []
    for token in re.split(r"[,\n;]+", text):
        candidate = str(token or "").strip()
        if candidate and candidate not in items:
            items.append(candidate)
    return items


def parse_yt_dlp_browser_spec(raw_spec: Any) -> Tuple[Any, ...] | None:
    """Parse a yt-dlp cookies-from-browser spec into its option tuple."""
    spec = str(raw_spec or "").strip()
    if not spec:
        return None
    parts = [part.strip() for part in spec.split(":")]
    browser = str(parts[0] or "").strip().lower()
    if not browser or browser not in SUPPORTED_YTDLP_COOKIE_BROWSERS:
        return None

    profile = parts[1] if len(parts) > 1 and parts[1] else None
    keyring = parts[2] if len(parts) > 2 and parts[2] else None
    container = parts[3] if len(parts) > 3 and parts[3] else None
    return (browser, profile, keyring, container)


def _cookie_domain_from_host(host_text: str) -> str:
    if host_text.endswith(".douyin.com"):
        return ".douyin.com"
    if host_text.endswith(".iesdouyin.com"):
        return ".iesdouyin.com"
    if host_text.startswith("."):
        return host_text
    return f".{host_text}"


def write_ytdlp_cookiefile_from_header(
    cookie_header: str,
    host: str,
    *,
    cache_root: Path,
) -> Path | None:
    """Write a Netscape cookie file generated from a raw Cookie header."""
    header_text = str(cookie_header or "").strip()
    host_text = str(host or "").strip().lower()
    if not header_text or not host_text:
        return None
    host_text = host_text.split(":", 1)[0]
    if not host_text:
        return None

    cookie_items: List[Tuple[str, str]] = []
    for segment in header_text.split(";"):
        pair = str(segment or "").strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if not key_text:
            continue
        cookie_items.append((key_text, value_text))
    if not cookie_items:
        return None

    cache_dir = Path(cache_root).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(f"{host_text}|{header_text}".encode("utf-8")).hexdigest()[:16]
    cookie_file = cache_dir / f"{host_text}_{cache_key}.cookies.txt"
    cookie_domain = _cookie_domain_from_host(host_text)
    lines = ["# Netscape HTTP Cookie File", ""]
    for key_text, value_text in cookie_items:
        lines.append(f"{cookie_domain}\tTRUE\t/\tTRUE\t0\t{key_text}\t{value_text}")
    cookie_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cookie_file


def build_yt_dlp_cookie_sources(
    raw_url: str = "",
    *,
    cookie_header: str = "",
    cookies_file: str = "",
    cookies_from_browser: str = "",
    prefer_browser_cookies: bool = False,
    browser_fallbacks: str = "",
    cache_root: Path,
    logger_obj: logging.Logger | None = None,
) -> List[Dict[str, Any]]:
    """Build ordered, deduplicated yt-dlp cookie source option dictionaries."""
    sources: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    def _add_source(label: str, opts: Dict[str, Any]) -> None:
        normalized_label = str(label or "").strip() or "unknown"
        if "cookiefile" in opts:
            key = ("file", str(opts.get("cookiefile", "")).strip().lower())
        elif "cookiesfrombrowser" in opts:
            browser_tuple = tuple(opts.get("cookiesfrombrowser") or ())
            key = ("browser", "|".join(str(item or "") for item in browser_tuple).lower())
        else:
            key = ("none", "none")
        if key in seen:
            return
        seen.add(key)
        payload = dict(opts)
        payload["label"] = normalized_label
        sources.append(payload)

    parsed = urlparse(str(raw_url or "").strip())
    host = str(parsed.netloc or "").strip()
    if cookie_header and host:
        generated_cookie_file = write_ytdlp_cookiefile_from_header(
            cookie_header,
            host,
            cache_root=cache_root,
        )
        if generated_cookie_file is not None and generated_cookie_file.exists():
            _add_source(
                f"cookieheader:{generated_cookie_file.name}",
                {"cookiefile": str(generated_cookie_file)},
            )

    cookie_file_text = str(cookies_file or "").strip()
    if cookie_file_text:
        cookie_path = Path(cookie_file_text).expanduser().resolve(strict=False)
        if cookie_path.exists() and cookie_path.is_file():
            _add_source(
                f"cookiefile:{cookie_path.name}",
                {"cookiefile": str(cookie_path)},
            )
        elif logger_obj is not None:
            logger_obj.warning("YTDLP_COOKIES_FILE ???????: %s", cookie_path)

    for browser_spec in parse_csv_text(cookies_from_browser):
        parsed_spec = parse_yt_dlp_browser_spec(browser_spec)
        if parsed_spec is not None:
            _add_source(
                f"browser:{parsed_spec[0]}",
                {"cookiesfrombrowser": parsed_spec},
            )

    if prefer_browser_cookies:
        for browser_spec in parse_csv_text(browser_fallbacks):
            parsed_spec = parse_yt_dlp_browser_spec(browser_spec)
            if parsed_spec is not None:
                _add_source(
                    f"browser:{parsed_spec[0]}",
                    {"cookiesfrombrowser": parsed_spec},
                )

    _add_source("no_cookies", {})
    return sources
