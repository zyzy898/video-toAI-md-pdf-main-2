from pathlib import Path

from services.ytdlp_cookies import (
    build_yt_dlp_cookie_sources,
    parse_csv_text,
    parse_yt_dlp_browser_spec,
    write_ytdlp_cookiefile_from_header,
)


def test_parse_csv_text_splits_common_separators_and_deduplicates():
    assert parse_csv_text("chrome, firefox; chrome\nedge") == [
        "chrome",
        "firefox",
        "edge",
    ]
    assert parse_csv_text("  ") == []


def test_parse_yt_dlp_browser_spec_validates_supported_browser_and_parts():
    assert parse_yt_dlp_browser_spec("Chrome:Default:keyring:container") == (
        "chrome",
        "Default",
        "keyring",
        "container",
    )
    assert parse_yt_dlp_browser_spec("firefox") == ("firefox", None, None, None)
    assert parse_yt_dlp_browser_spec("unknown:Default") is None


def test_write_ytdlp_cookiefile_from_header_uses_netscape_cookie_format(tmp_path: Path):
    cookie_file = write_ytdlp_cookiefile_from_header(
        "sid=abc; empty; uid=42",
        "www.douyin.com:443",
        cache_root=tmp_path,
    )

    assert cookie_file is not None
    assert cookie_file.parent == tmp_path.resolve()
    content = cookie_file.read_text(encoding="utf-8")
    assert content.startswith("# Netscape HTTP Cookie File")
    assert ".douyin.com\tTRUE\t/\tTRUE\t0\tsid\tabc" in content
    assert ".douyin.com\tTRUE\t/\tTRUE\t0\tuid\t42" in content
    assert "empty" not in content


def test_build_yt_dlp_cookie_sources_deduplicates_and_appends_no_cookie_fallback(tmp_path: Path):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# cookies", encoding="utf-8")

    sources = build_yt_dlp_cookie_sources(
        raw_url="https://www.douyin.com/video/123",
        cookie_header="sid=abc",
        cookies_file=str(cookie_file),
        cookies_from_browser="chrome,chrome",
        prefer_browser_cookies=True,
        browser_fallbacks="edge;invalid",
        cache_root=tmp_path / "generated",
    )

    labels = [source["label"] for source in sources]
    assert labels[0].startswith("cookieheader:")
    assert labels[1] == "cookiefile:cookies.txt"
    assert labels[2] == "browser:chrome"
    assert labels[3] == "browser:edge"
    assert labels[-1] == "no_cookies"
    assert len([source for source in sources if source["label"] == "browser:chrome"]) == 1
