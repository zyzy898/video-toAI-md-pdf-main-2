import html
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

_SHARE_LINK_PATTERNS = (
    r"v\.douyin\.com/[A-Za-z0-9/_-]+",
    r'(?:www\.)?douyin\.com/[^\s"\'<>]+',
    r'(?:www\.)?iesdouyin\.com/[^\s"\'<>]+',
    r"xhslink\.com/[A-Za-z0-9/_-]+",
    r'(?:www\.)?xiaohongshu\.com/[^\s"\'<>]+',
    r'b23\.tv/[^\s"\'<>]+',
    r'(?:www\.)?bilibili\.com/[^\s"\'<>]+',
)
_MEDIA_ID_KEYS = ("modal_id", "aweme_id", "video_id", "item_id")
_MEDIA_PATH_PATTERN = r"/(?:video|note|share/video)/([0-9]{8,25})"
_MEDIA_TEXT_PATTERNS = (
    r"(?:modal_id|aweme_id|video_id|item_id)\D{0,24}([0-9]{8,25})",
    _MEDIA_PATH_PATTERN,
)
_VIDEO_URL_KEYS = {
    "contenturl",
    "embedurl",
    "url",
    "src",
    "playaddr",
    "play_addr",
    "playurl",
    "play_url",
    "downloadurl",
    "download_url",
}


def normalize_source_url(raw_url: Any) -> str:
    url_text = str(raw_url or "").strip()
    if not url_text:
        raise ValueError("empty video URL")
    if len(url_text) > 1500:
        raise ValueError("video URL is too long")

    if not re.match(r"^https?://", url_text, flags=re.IGNORECASE):
        match = re.search(r'https?://[^\s"\'<>]+', url_text, flags=re.IGNORECASE)
        if match:
            url_text = match.group(0).strip()
        else:
            extracted = ""
            for pattern in _SHARE_LINK_PATTERNS:
                candidate_match = re.search(pattern, url_text, flags=re.IGNORECASE)
                if candidate_match:
                    extracted = str(candidate_match.group(0) or "").strip()
                    break
            if extracted:
                url_text = f"https://{extracted.lstrip('/')}"

    url_text = url_text.lstrip(" \t\r\n<([{\"'")
    url_text = url_text.rstrip(" \t\r\n'\"),.;!?")
    parsed = urlparse(url_text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("only http/https video URLs are supported")
    return url_text


def extract_numeric_media_id(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    digits = re.sub(r"[^\d]", "", text)
    if len(digits) < 8:
        return ""
    return digits


def build_source_url_candidates(raw_url: Any) -> list[str]:
    normalized = normalize_source_url(raw_url)
    candidates: list[str] = [normalized]
    parsed = urlparse(normalized)
    host = str(parsed.netloc or "").lower()
    path = str(parsed.path or "")
    query_map = parse_qs(str(parsed.query or ""), keep_blank_values=False)

    def append_candidate(url_text: str) -> None:
        text = str(url_text or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    if "douyin.com" in host or "iesdouyin.com" in host:
        media_id = ""
        for key in _MEDIA_ID_KEYS:
            values = query_map.get(key) or []
            if not values:
                continue
            candidate_id = extract_numeric_media_id(values[0])
            if candidate_id:
                media_id = candidate_id
                break
        if not media_id:
            fallback_match = re.search(
                r"(?:modal_id|aweme_id|video_id|item_id)=([0-9]{8,25})",
                normalized,
            )
            if fallback_match:
                media_id = fallback_match.group(1)
        if not media_id:
            path_match = re.search(_MEDIA_PATH_PATTERN, path)
            if path_match:
                media_id = path_match.group(1)

        if media_id:
            append_candidate(f"https://www.douyin.com/video/{media_id}")
            append_candidate(f"https://www.iesdouyin.com/share/video/{media_id}/")

    return candidates


def append_unique_url_candidate(candidates: list[str], candidate_url: Any, *, base_url: str = "") -> None:
    text = html.unescape(str(candidate_url or "").strip())
    if not text:
        return
    text = (
        text.replace("\\/", "/")
        .replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .rstrip(" \t\r\n'\"),.;!?")
    )
    if not text:
        return
    if text.startswith("//"):
        text = f"https:{text}"
    if text.startswith("/") and base_url:
        text = urljoin(base_url, text)
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return
    if text not in candidates:
        candidates.append(text)


def extract_media_ids_from_text(raw_text: Any) -> list[str]:
    text = str(raw_text or "")
    if not text:
        return []

    ids: list[str] = []
    for pattern in _MEDIA_TEXT_PATTERNS:
        for match in re.findall(pattern, text):
            media_id = extract_numeric_media_id(match)
            if media_id and media_id not in ids:
                ids.append(media_id)
    return ids


def extract_media_ids_from_url(raw_url: Any) -> list[str]:
    url_text = str(raw_url or "").strip()
    if not url_text:
        return []
    parsed = urlparse(url_text)
    host = str(parsed.netloc or "").lower()
    query_map = parse_qs(str(parsed.query or ""), keep_blank_values=False)

    ids: list[str] = []
    for key in _MEDIA_ID_KEYS:
        values = query_map.get(key) or []
        for value in values:
            media_id = extract_numeric_media_id(value)
            if media_id and media_id not in ids:
                ids.append(media_id)

    path = str(parsed.path or "")
    path_match = re.search(_MEDIA_PATH_PATTERN, path)
    if path_match:
        media_id = extract_numeric_media_id(path_match.group(1))
        if media_id and media_id not in ids:
            ids.append(media_id)

    if not ids and ("douyin.com" in host or "iesdouyin.com" in host):
        ids = extract_media_ids_from_text(url_text)
    return ids[:8]


def url_contains_media_id(raw_url: Any, media_id: str) -> bool:
    target = extract_numeric_media_id(media_id)
    if not target:
        return False
    text = str(raw_url or "")
    if target in text:
        return True
    for item in extract_media_ids_from_url(raw_url):
        if item == target:
            return True
    return False


def looks_like_video_candidate_url(raw_url: Any) -> bool:
    text = str(raw_url or "").strip().lower()
    if not text:
        return False
    if re.search(r"\.(mp4|m3u8|mov|webm)(?:$|[?#])", text):
        return True
    if any(token in text for token in ("/video/", "/share/video/", "/note/")):
        return True
    if any(token in text for token in ("modal_id=", "aweme_id=", "video_id=", "item_id=")):
        return True
    return False


def extract_video_urls_from_json_payload(
    payload: Any,
    collected: list[str],
    *,
    base_url: str = "",
    key_hint: str = "",
) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            extract_video_urls_from_json_payload(
                value,
                collected,
                base_url=base_url,
                key_hint=str(key or "").strip().lower(),
            )
        return
    if isinstance(payload, list):
        for value in payload:
            extract_video_urls_from_json_payload(value, collected, base_url=base_url, key_hint=key_hint)
        return
    if not isinstance(payload, str):
        return

    normalized = html.unescape(payload).strip()
    if not normalized:
        return

    if key_hint in _VIDEO_URL_KEYS or looks_like_video_candidate_url(normalized):
        append_unique_url_candidate(collected, normalized, base_url=base_url)
