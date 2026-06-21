import asyncio
import base64
import html
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
import random
import re
import secrets
import shutil
import socket
import subprocess
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from pathlib import Path
from threading import Lock, RLock, Thread
from typing import Any, Callable, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from Scrapling_download.platform_link_downloader import PlatformLinkDownloader
SCRAPLING_READER_AVAILABLE = True
try:
    from Scrapling_download.scrapling_page_reader import ScraplingPageReader, ScraplingReaderSettings
except Exception:
    SCRAPLING_READER_AVAILABLE = False

    class ScraplingReaderSettings:  # type: ignore[override]
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class ScraplingPageReader:  # type: ignore[override]
        def __init__(self, *, logger_obj: Any, settings_provider: Callable[[], Any]) -> None:
            self._logger = logger_obj
            self._settings_provider = settings_provider

        def fetch_attempts(self, raw_url: str) -> List[Any]:
            return []

from video_analyzer_agent import VideoAnalyzerAgent
from llm_client import ProviderFeatureUnsupportedError

# Centralized configuration: env loading, path roots, and all tunable
# constants live in config.py. Importing it also calls load_dotenv() and
# ensures the runtime directories exist.
from config import *  # noqa: F401,F403  (constants/helpers re-exported via __all__)
from utils import _normalize_risk_score, _safe_float, _safe_int
from path_utils import _assert_within, _resolve_output_dir, _resolve_upload_filepath
from services.progress import ProgressStateService
from services.risk_fallback_env import RiskFallbackEnvService
from services.risk_blocklist import RiskBlocklistService
from services.risk_cache import RiskResultCacheService
from services.history import HistoryService, HistoryRetentionCleanupService
from services.upload_session import UploadSessionService, UploadVideoAutoCleanupService
from services.segment_policy import (
    _apply_video_segment_processing_guardrails,
    _build_segment_policy_reject_payload,
    _build_video_segment_policy,
    _evaluate_batch_segment_policy,
    _probe_video_duration_seconds,
)
from services.video_preprocess import _prepare_long_video_analysis_source
from services.step_quality import _resolve_quality_score
from services.media_bundle import (
    _append_output_bundle_to_zip,
    _build_output_media_bundle,
    _ensure_subtitle_exports,
    _find_output_subtitle_file,
    _format_seconds_to_mmss,
    _parse_srt_file_entries,
)
from services.text_risk import _run_text_fallback_risk_gate
from services.media_validation import is_valid_video_content

app = Flask(__name__)
# 优先从环境变量读取，缺失时生成随机密钥（避免硬编码可预测密钥被伪造）
_secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
if not _secret_key:
    _secret_key = secrets.token_hex(32)
app.secret_key = _secret_key

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_ROOT)
app.config["OUTPUT_FOLDER"] = str(OUTPUT_ROOT)



logger = logging.getLogger(__name__)
history_lock = RLock()
upload_session_lock = RLock()
batch_progress_lock = Lock()
batch_progress_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}
single_progress_lock = Lock()
single_progress_by_owner: Dict[str, Dict[str, Dict[str, Any]]] = {}
upload_memory_buffers: Dict[str, Dict[int, bytes]] = {}
upload_memory_reserved_bytes: Dict[str, int] = {}
upload_memory_reserved_total_bytes = 0
risk_blocklist_lock = RLock()
risk_result_cache_lock = RLock()



risk_fallback_env_service = RiskFallbackEnvService(
    env_path=ENV_FILE_PATH,
    block_marker=RISK_FALLBACK_ENV_BLOCK_MARKER,
    legacy_marker=RISK_FALLBACK_ENV_BLOCK_MARKER_LEGACY,
    env_keys=RISK_FALLBACK_ENV_KEYS,
    logger_obj=logger,
)
progress_state_service = ProgressStateService(
    batch_state_map=batch_progress_by_owner,
    batch_lock_obj=batch_progress_lock,
    single_state_map=single_progress_by_owner,
    single_lock_obj=single_progress_lock,
    owner_pattern=HISTORY_OWNER_PATTERN,
    owner_max_len=HISTORY_OWNER_MAX_LEN,
)


def _ensure_risk_fallback_env_file() -> None:
    risk_fallback_env_service.ensure_env_file()


def _read_risk_fallback_env_model_options() -> Tuple[str, str, str]:
    return risk_fallback_env_service.read_model_options()


_ensure_risk_fallback_env_file()


class ContentPolicyBlockedError(RuntimeError):
    def __init__(self, message: str, risk: Dict[str, Any]):
        super().__init__(message)
        self.risk = risk


def _resolve_progress_task_id(raw_task_id: Any) -> str:
    return progress_state_service.resolve_task_id(raw_task_id)


def _update_batch_progress(owner_id: str, task_id: str, **kwargs: Any) -> None:
    progress_state_service.update_batch(owner_id, task_id, **kwargs)


def _update_single_progress(owner_id: str, task_id: str, **kwargs: Any) -> None:
    progress_state_service.update_single(owner_id, task_id, **kwargs)



def _normalize_source_url(raw_url: Any) -> str:
    url_text = str(raw_url or "").strip()
    if not url_text:
        raise ValueError("请输入视频链接")
    if len(url_text) > 1500:
        raise ValueError("链接长度超出限制，请精简后重试")

    if not re.match(r"^https?://", url_text, flags=re.IGNORECASE):
        match = re.search(r"https?://[^\s\"'<>]+", url_text, flags=re.IGNORECASE)
        if match:
            url_text = match.group(0).strip()
        else:
            share_link_patterns = (
                r"v\.douyin\.com/[A-Za-z0-9/_-]+",
                r"(?:www\.)?douyin\.com/[^\s\"'<>]+",
                r"(?:www\.)?iesdouyin\.com/[^\s\"'<>]+",
                r"xhslink\.com/[A-Za-z0-9/_-]+",
                r"(?:www\.)?xiaohongshu\.com/[^\s\"'<>]+",
                r"b23\.tv/[^\s\"'<>]+",
                r"(?:www\.)?bilibili\.com/[^\s\"'<>]+",
            )
            extracted = ""
            for pattern in share_link_patterns:
                candidate_match = re.search(pattern, url_text, flags=re.IGNORECASE)
                if candidate_match:
                    extracted = str(candidate_match.group(0) or "").strip()
                    break
            if extracted:
                url_text = f"https://{extracted.lstrip('/')}"

    url_text = url_text.lstrip(" \t\r\n<([{\"'“‘")
    url_text = url_text.rstrip(" \t\r\n'\"),.;!?，。！？；：】）》」")
    parsed = urlparse(url_text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("仅支持 http/https 视频链接")
    return url_text


def _extract_numeric_media_id(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    digits = re.sub(r"[^\d]", "", text)
    if len(digits) < 8:
        return ""
    return digits


def _build_source_url_candidates(raw_url: Any) -> List[str]:
    normalized = _normalize_source_url(raw_url)
    candidates: List[str] = [normalized]
    parsed = urlparse(normalized)
    host = str(parsed.netloc or "").lower()
    path = str(parsed.path or "")
    query_map = parse_qs(str(parsed.query or ""), keep_blank_values=False)

    def _append_candidate(url_text: str) -> None:
        text = str(url_text or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    if "douyin.com" in host or "iesdouyin.com" in host:
        media_id = ""
        for key in ("modal_id", "aweme_id", "video_id", "item_id"):
            values = query_map.get(key) or []
            if not values:
                continue
            candidate_id = _extract_numeric_media_id(values[0])
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
            path_match = re.search(r"/(?:video|note|share/video)/(\d{8,25})", path)
            if path_match:
                media_id = path_match.group(1)

        if media_id:
            _append_candidate(f"https://www.douyin.com/video/{media_id}")
            _append_candidate(f"https://www.iesdouyin.com/share/video/{media_id}/")

    return candidates


def _append_unique_url_candidate(
    candidates: List[str],
    candidate_url: Any,
    *,
    base_url: str = "",
) -> None:
    text = html.unescape(str(candidate_url or "").strip())
    if not text:
        return
    text = (
        text.replace("\\/", "/")
        .replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .rstrip(" \t\r\n'\"),.;!?，。！？；：】）")
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


def _extract_media_ids_from_text(raw_text: Any) -> List[str]:
    text = str(raw_text or "")
    if not text:
        return []

    patterns = (
        r"(?:modal_id|aweme_id|video_id|item_id)\D{0,24}([0-9]{8,25})",
        r"/(?:video|note|share/video)/([0-9]{8,25})",
    )
    ids: List[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            media_id = _extract_numeric_media_id(match)
            if media_id and media_id not in ids:
                ids.append(media_id)
    return ids


def _extract_media_ids_from_url(raw_url: Any) -> List[str]:
    url_text = str(raw_url or "").strip()
    if not url_text:
        return []
    parsed = urlparse(url_text)
    host = str(parsed.netloc or "").lower()
    query_map = parse_qs(str(parsed.query or ""), keep_blank_values=False)

    ids: List[str] = []
    for key in ("modal_id", "aweme_id", "video_id", "item_id"):
        values = query_map.get(key) or []
        for value in values:
            media_id = _extract_numeric_media_id(value)
            if media_id and media_id not in ids:
                ids.append(media_id)

    path = str(parsed.path or "")
    path_match = re.search(r"/(?:video|note|share/video)/([0-9]{8,25})", path)
    if path_match:
        media_id = _extract_numeric_media_id(path_match.group(1))
        if media_id and media_id not in ids:
            ids.append(media_id)

    if not ids and ("douyin.com" in host or "iesdouyin.com" in host):
        ids = _extract_media_ids_from_text(url_text)
    return ids[:8]


def _url_contains_media_id(raw_url: Any, media_id: str) -> bool:
    target = _extract_numeric_media_id(media_id)
    if not target:
        return False
    text = str(raw_url or "")
    if target in text:
        return True
    for item in _extract_media_ids_from_url(raw_url):
        if item == target:
            return True
    return False


def _looks_like_video_candidate_url(raw_url: Any) -> bool:
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


def _extract_video_urls_from_json_payload(
    payload: Any,
    collected: List[str],
    *,
    base_url: str = "",
    key_hint: str = "",
) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            _extract_video_urls_from_json_payload(
                value,
                collected,
                base_url=base_url,
                key_hint=str(key or "").strip().lower(),
            )
        return
    if isinstance(payload, list):
        for value in payload:
            _extract_video_urls_from_json_payload(
                value, collected, base_url=base_url, key_hint=key_hint
            )
        return
    if not isinstance(payload, str):
        return

    normalized = html.unescape(payload).strip()
    if not normalized:
        return

    likely_video_key = key_hint in {
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
    if likely_video_key or _looks_like_video_candidate_url(normalized):
        _append_unique_url_candidate(collected, normalized, base_url=base_url)


def _parse_env_mapping(raw_value: str) -> Dict[str, str]:
    text = str(raw_value or "").strip()
    if not text:
        return {}

    parsed: Dict[str, Any] = {}
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        parsed = data
    else:
        parsed = {}
        for token in re.split(r"[;\n]+", text):
            part = str(token or "").strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            key_text = str(key or "").strip()
            value_text = str(value or "").strip()
            if key_text:
                parsed[key_text] = value_text

    normalized: Dict[str, str] = {}
    for key, value in parsed.items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and value_text:
            normalized[key_text] = value_text
    return normalized


def _build_scrapling_reader_settings() -> ScraplingReaderSettings:
    return ScraplingReaderSettings(
        fetch_mode=SCRAPE_FETCH_MODE,
        timeout_seconds=SCRAPE_TIMEOUT_SECONDS,
        retries=SCRAPE_RETRIES,
        retry_delay_seconds=SCRAPE_RETRY_DELAY_SECONDS,
        dynamic_wait_seconds=SCRAPE_DYNAMIC_WAIT_SECONDS,
        dynamic_headless=SCRAPE_DYNAMIC_HEADLESS,
        dynamic_disable_resources=SCRAPE_DYNAMIC_DISABLE_RESOURCES,
        dynamic_network_idle=SCRAPE_DYNAMIC_NETWORK_IDLE,
        impersonate=SCRAPE_IMPERSONATE,
        proxy_url=SCRAPE_PROXY_URL,
        user_agent=SCRAPE_USER_AGENT,
        extra_headers=_parse_env_mapping(SCRAPE_EXTRA_HEADERS_JSON),
        cookies=_parse_env_mapping(SCRAPE_COOKIES_JSON),
        session_max_pages=SCRAPE_STEALTH_SESSION_MAX_PAGES,
        session_max_requests=SCRAPE_STEALTH_SESSION_MAX_REQUESTS,
        session_idle_ttl_seconds=SCRAPE_STEALTH_SESSION_IDLE_TTL_SECONDS,
        session_real_chrome=SCRAPE_STEALTH_REAL_CHROME,
        session_block_webrtc=SCRAPE_STEALTH_BLOCK_WEBRTC,
        session_solve_cloudflare=SCRAPE_STEALTH_SOLVE_CLOUDFLARE,
        session_locale=SCRAPE_STEALTH_LOCALE,
        session_timezone_id=SCRAPE_STEALTH_TIMEZONE_ID,
    )


SCRAPLING_PAGE_READER = ScraplingPageReader(
    logger_obj=logger,
    settings_provider=_build_scrapling_reader_settings,
)
PLATFORM_LINK_DOWNLOADER = PlatformLinkDownloader(logger_obj=logger, use_llm=True)


def _detect_human_verification_signals(
    status_code: int,
    final_url: str,
    html_text: str,
) -> List[str]:
    signals: List[str] = []
    if status_code in {403, 429, 503}:
        signals.append(f"http_{status_code}")

    final_url_lower = str(final_url or "").strip().lower()
    if any(token in final_url_lower for token in ("captcha", "challenge", "verify", "security")):
        signals.append("url_challenge_hint")

    snapshot = str(html_text or "").lower()[:120000]
    pattern_map = {
        "captcha": r"\bcaptcha\b",
        "turnstile": r"\bturnstile\b",
        "cf_challenge": r"cf[-_]?challenge|cloudflare",
        "human_check_en": r"verify you are human|security check|access denied",
        "human_check_zh": r"人机验证|安全验证|请完成验证|滑块验证|行为验证|风控校验",
    }
    for label, pattern in pattern_map.items():
        if re.search(pattern, snapshot, flags=re.IGNORECASE):
            signals.append(label)

    unique: List[str] = []
    for item in signals:
        text = str(item or "").strip()
        if text and text not in unique:
            unique.append(text)
    return unique[:8]


def _read_scrape_env_model_options() -> Tuple[str, str, str]:
    api_key = _env_text(
        (
            "SCRAPE_MODEL_API_KEY",
            "MODEL_API_KEY",
            "ARK_API_KEY",
            "OPENAI_API_KEY",
            "RISK_FALLBACK_API_KEY",
        ),
        "",
    )
    model_name = _env_text(
        ("SCRAPE_MODEL_NAME", "MODEL_NAME", "RISK_FALLBACK_MODEL_NAME"),
        "",
    )
    model_base_url = _env_text(
        ("SCRAPE_MODEL_BASE_URL", "MODEL_BASE_URL", "RISK_FALLBACK_MODEL_BASE_URL"),
        "",
    )
    return (
        str(api_key or "").strip(),
        str(model_name or "").strip(),
        str(model_base_url or "").strip(),
    )


def _extract_video_candidates_with_env_model(
    page_url: str,
    html_text: str,
    page_title: str = "",
) -> Dict[str, Any]:
    if not SCRAPE_MODEL_PARSE_ENABLED:
        return {}

    api_key, model_name, model_base_url = _read_scrape_env_model_options()
    if not api_key or not model_name or not model_base_url:
        return {}

    snapshot = str(html_text or "").strip()
    if not snapshot:
        return {}
    snapshot = snapshot[:SCRAPE_MODEL_HTML_MAX_CHARS]

    agent = VideoAnalyzerAgent(
        api_key=api_key,
        whisper_model="tiny",
        model_name=model_name,
        model_base_url=model_base_url,
    )
    prompt_schema = {
        "candidate_urls": ["https://example.com/video.mp4"],
        "media_ids": ["1234567890"],
        "confidence_note": "short reasoning",
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You extract playable video URLs and video IDs from HTML text. "
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Page URL: {page_url}\n"
                f"Page title: {page_title}\n"
                f"Return strict JSON with schema: {json.dumps(prompt_schema, ensure_ascii=False)}\n"
                "Rules: candidate_urls must be absolute http/https URLs; "
                "media_ids should only contain digits.\n"
                f"HTML snapshot:\n{snapshot}"
            ),
        },
    ]

    raw_result = _run_async(agent._chat_completion_text(messages, temperature=0.0))
    parsed = agent._parse_json_object_response(raw_result)
    if not isinstance(parsed, dict):
        return {}

    candidate_urls: List[str] = []
    for item in parsed.get("candidate_urls", []) or []:
        text = str(item or "").strip()
        if text:
            candidate_urls.append(text)

    media_ids: List[str] = []
    for item in parsed.get("media_ids", []) or []:
        media_id = _extract_numeric_media_id(item)
        if media_id and media_id not in media_ids:
            media_ids.append(media_id)

    return {
        "candidate_urls": candidate_urls[:24],
        "media_ids": media_ids[:24],
        "confidence_note": str(parsed.get("confidence_note", "")).strip(),
        "model_name": model_name,
    }


def _parse_csv_text(raw_value: Any) -> List[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    items: List[str] = []
    for token in re.split(r"[,\n;]+", text):
        candidate = str(token or "").strip()
        if candidate and candidate not in items:
            items.append(candidate)
    return items


def _parse_yt_dlp_browser_spec(raw_spec: Any) -> Tuple[Any, ...] | None:
    spec = str(raw_spec or "").strip()
    if not spec:
        return None
    parts = [part.strip() for part in spec.split(":")]
    browser = str(parts[0] or "").strip().lower()
    if not browser:
        return None

    # Supported browsers in yt-dlp cookies module.
    supported = {
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
    if browser not in supported:
        return None

    profile = parts[1] if len(parts) > 1 and parts[1] else None
    keyring = parts[2] if len(parts) > 2 and parts[2] else None
    container = parts[3] if len(parts) > 3 and parts[3] else None
    return (browser, profile, keyring, container)


def _write_ytdlp_cookiefile_from_header(cookie_header: str, host: str) -> Path | None:
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

    cache_dir = (UPLOAD_STAGING_ROOT / ".yt_dlp_cookie_cache").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(f"{host_text}|{header_text}".encode("utf-8")).hexdigest()[:16]
    cookie_file = cache_dir / f"{host_text}_{cache_key}.cookies.txt"
    lines = ["# Netscape HTTP Cookie File", ""]
    cookie_domain = host_text
    if host_text.endswith(".douyin.com"):
        cookie_domain = ".douyin.com"
    elif host_text.endswith(".iesdouyin.com"):
        cookie_domain = ".iesdouyin.com"
    elif host_text.startswith("."):
        cookie_domain = host_text
    else:
        cookie_domain = f".{host_text}"
    for key_text, value_text in cookie_items:
        lines.append(f"{cookie_domain}\tTRUE\t/\tTRUE\t0\t{key_text}\t{value_text}")
    cookie_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cookie_file


def _build_yt_dlp_cookie_sources(raw_url: str = "") -> List[Dict[str, Any]]:
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
    if YTDLP_COOKIE_HEADER and host:
        generated_cookie_file = _write_ytdlp_cookiefile_from_header(
            YTDLP_COOKIE_HEADER, host
        )
        if generated_cookie_file is not None and generated_cookie_file.exists():
            _add_source(
                f"cookieheader:{generated_cookie_file.name}",
                {"cookiefile": str(generated_cookie_file)},
            )

    cookies_file = str(YTDLP_COOKIES_FILE or "").strip()
    if cookies_file:
        cookie_path = Path(cookies_file).expanduser().resolve(strict=False)
        if cookie_path.exists() and cookie_path.is_file():
            _add_source(
                f"cookiefile:{cookie_path.name}",
                {"cookiefile": str(cookie_path)},
            )
        else:
            logger.warning("YTDLP_COOKIES_FILE 不存在或不可读: %s", cookie_path)

    for browser_spec in _parse_csv_text(YTDLP_COOKIES_FROM_BROWSER):
        parsed = _parse_yt_dlp_browser_spec(browser_spec)
        if parsed is not None:
            _add_source(
                f"browser:{parsed[0]}",
                {"cookiesfrombrowser": parsed},
            )

    if YTDLP_PREFER_BROWSER_COOKIES:
        for browser_spec in _parse_csv_text(YTDLP_BROWSER_FALLBACKS):
            parsed = _parse_yt_dlp_browser_spec(browser_spec)
            if parsed is not None:
                _add_source(
                    f"browser:{parsed[0]}",
                    {"cookiesfrombrowser": parsed},
                )

    _add_source("no_cookies", {})
    return sources


def _scrape_page_info_with_scrapling(raw_url: str) -> Dict[str, Any]:
    attempts = SCRAPLING_PAGE_READER.fetch_attempts(raw_url)

    def _extract_from_response(response_obj: Any, method_tag: str) -> Dict[str, Any]:
        status_code = _safe_int(getattr(response_obj, "status", 0), 0, 0)
        final_url = str(getattr(response_obj, "url", "")).strip() or raw_url
        base_url = final_url or raw_url

        def _css_values(selector: str) -> List[str]:
            try:
                selected = response_obj.css(selector)
            except Exception:
                return []
            try:
                values = selected.getall()
            except Exception:
                try:
                    single = selected.get()
                except Exception:
                    single = ""
                values = [single] if single else []
            results: List[str] = []
            for value in values:
                text = str(value or "").strip()
                if text:
                    results.append(text)
            return results

        discovered_urls: List[str] = []
        _append_unique_url_candidate(discovered_urls, final_url, base_url=base_url)

        title_candidates = (
            _css_values("meta[property='og:title']::attr(content)")
            + _css_values("meta[name='twitter:title']::attr(content)")
            + _css_values("title::text")
        )
        page_title = str(title_candidates[0]).strip() if title_candidates else ""

        canonical_candidates = _css_values("link[rel='canonical']::attr(href)") + _css_values(
            "meta[property='og:url']::attr(content)"
        )
        canonical_url = ""
        for candidate in canonical_candidates:
            before_len = len(discovered_urls)
            _append_unique_url_candidate(discovered_urls, candidate, base_url=base_url)
            if len(discovered_urls) > before_len and not canonical_url:
                canonical_url = discovered_urls[-1]

        for selector in (
            "meta[property='og:video']::attr(content)",
            "meta[property='og:video:url']::attr(content)",
            "meta[property='og:video:secure_url']::attr(content)",
            "meta[name='twitter:player:stream']::attr(content)",
            "video::attr(src)",
            "video source::attr(src)",
        ):
            for candidate in _css_values(selector):
                _append_unique_url_candidate(discovered_urls, candidate, base_url=base_url)

        html_content = str(getattr(response_obj, "html_content", "") or "")
        if not html_content:
            body = getattr(response_obj, "body", b"")
            if isinstance(body, bytes):
                html_content = body.decode("utf-8", errors="ignore")
            else:
                html_content = str(body or "")
        if not html_content:
            html_content = str(getattr(response_obj, "text", "") or "")

        for pattern in (
            r"https?://[^\s\"'<>\\]+(?:\.mp4|\.m3u8)(?:\?[^\s\"'<>\\]*)?",
            r"https?://[^\s\"'<>\\]+/(?:video|note|share/video)/\d{8,25}[^\s\"'<>\\]*",
            r"https?://[^\s\"'<>\\]+(?:modal_id|aweme_id|video_id|item_id)=\d{8,25}[^\s\"'<>\\]*",
        ):
            for found_url in re.findall(pattern, html_content, flags=re.IGNORECASE):
                _append_unique_url_candidate(discovered_urls, found_url, base_url=base_url)

        script_json_blocks = _css_values("script[type='application/ld+json']::text")
        for script_text in script_json_blocks:
            script_text_clean = str(script_text or "").strip()
            if not script_text_clean:
                continue
            try:
                payload = json.loads(script_text_clean)
            except Exception:
                for found_url in re.findall(
                    r"https?://[^\s\"'<>\\]+", script_text_clean, flags=re.IGNORECASE
                ):
                    if _looks_like_video_candidate_url(found_url):
                        _append_unique_url_candidate(
                            discovered_urls, found_url, base_url=base_url
                        )
                continue
            _extract_video_urls_from_json_payload(
                payload, discovered_urls, base_url=base_url, key_hint=""
            )

        media_ids = _extract_media_ids_from_text(
            "\n".join([raw_url, final_url, canonical_url, html_content[:600000]])
        )
        for media_id in media_ids:
            _append_unique_url_candidate(
                discovered_urls, f"https://www.douyin.com/video/{media_id}"
            )
            _append_unique_url_candidate(
                discovered_urls, f"https://www.iesdouyin.com/share/video/{media_id}/"
            )

        model_assist: Dict[str, Any] = {}
        if SCRAPE_MODEL_PARSE_ENABLED and html_content and len(discovered_urls) <= 2:
            try:
                model_assist = _extract_video_candidates_with_env_model(
                    final_url, html_content, page_title=page_title
                )
            except Exception as exc:
                model_assist = {"error": str(exc)}
            if isinstance(model_assist, dict):
                for found_url in model_assist.get("candidate_urls", []):
                    _append_unique_url_candidate(discovered_urls, found_url, base_url=base_url)
                for media_id in model_assist.get("media_ids", []):
                    media_id_text = _extract_numeric_media_id(media_id)
                    if not media_id_text:
                        continue
                    _append_unique_url_candidate(
                        discovered_urls, f"https://www.douyin.com/video/{media_id_text}"
                    )
                    _append_unique_url_candidate(
                        discovered_urls,
                        f"https://www.iesdouyin.com/share/video/{media_id_text}/",
                    )

        challenge_signals = _detect_human_verification_signals(
            status_code, final_url, html_content
        )
        return {
            "scraper": "scrapling_fetcher",
            "fetch_method": method_tag,
            "status_code": status_code,
            "final_url": final_url,
            "canonical_url": canonical_url,
            "page_title": page_title,
            "media_ids": media_ids[:12],
            "discovered_urls": discovered_urls[:60],
            "challenge_detected": bool(challenge_signals),
            "challenge_signals": challenge_signals,
            "model_assist_used": bool(model_assist),
            "model_assist_note": str(model_assist.get("confidence_note", "")).strip()
            if isinstance(model_assist, dict)
            else "",
        }

    fetch_errors: List[str] = []
    result_candidates: List[Dict[str, Any]] = []
    for attempt in attempts:
        method_tag = str(getattr(attempt, "method", "") or "").strip() or "unknown"
        response_obj = getattr(attempt, "response", None)
        error_text = str(getattr(attempt, "error", "") or "").strip()
        if response_obj is None:
            if error_text:
                fetch_errors.append(f"{method_tag}: {error_text}")
            continue
        try:
            parsed = _extract_from_response(response_obj, method_tag)
            result_candidates.append(parsed)
        except Exception as exc:
            fetch_errors.append(f"{method_tag}: {exc}")

    if not result_candidates:
        detail = "；".join(fetch_errors[:4]).strip() or "未知抓取错误"
        raise RuntimeError(f"scrapling 页面抓取失败：{detail}")

    def _score(item: Dict[str, Any]) -> Tuple[int, int, int]:
        discovered_count = len(item.get("discovered_urls", []) or [])
        challenge_flag = 0 if bool(item.get("challenge_detected", False)) else 1
        stealth_flag = 1 if str(item.get("fetch_method", "")).strip() == "stealth_session" else 0
        return challenge_flag, discovered_count, stealth_flag

    best = sorted(result_candidates, key=_score, reverse=True)[0]
    if fetch_errors:
        best["fetch_errors"] = fetch_errors[:4]
    return best


def _safe_video_filename(raw_name: str, fallback_stem: str = "url_video") -> str:
    safe_name = secure_filename(str(raw_name or "").strip())
    fallback = secure_filename(fallback_stem) or "url_video"
    stem = secure_filename(Path(safe_name).stem) if safe_name else fallback
    if not stem:
        stem = fallback
    suffix = Path(safe_name).suffix.lower() if safe_name else ""
    if not suffix or suffix.lstrip(".") not in ALLOWED_EXTENSIONS:
        suffix = ".mp4"
    return f"{stem}{suffix}"


def _extract_filename_from_content_disposition(header_value: str) -> str:
    text = str(header_value or "").strip()
    if not text:
        return ""

    match_ext = re.search(r"filename\*\s*=\s*([^;]+)", text, flags=re.IGNORECASE)
    if match_ext:
        value = match_ext.group(1).strip().strip('"')
        if "''" in value:
            value = value.split("''", 1)[1]
        return unquote(value).strip()

    match_plain = re.search(r'filename\s*=\s*"?([^";]+)"?', text, flags=re.IGNORECASE)
    if match_plain:
        return unquote(match_plain.group(1)).strip()
    return ""


def _guess_video_filename_from_url(
    raw_url: str,
    content_disposition: str = "",
    content_type: str = "",
    fallback: str = "url_video.mp4",
) -> str:
    candidate = _extract_filename_from_content_disposition(content_disposition)
    if not candidate:
        parsed = urlparse(raw_url)
        candidate = unquote(Path(parsed.path).name)

    safe_candidate = secure_filename(candidate)
    stem = secure_filename(Path(safe_candidate).stem) if safe_candidate else ""
    suffix = Path(safe_candidate).suffix.lower() if safe_candidate else ""
    if stem and suffix and suffix.lstrip(".") in ALLOWED_EXTENSIONS:
        return f"{stem}{suffix}"

    content_type_value = str(content_type or "").split(";")[0].strip().lower()
    guessed_ext = mimetypes.guess_extension(content_type_value) or ""
    guessed_ext = guessed_ext.lower()
    if guessed_ext.startswith(".") and guessed_ext[1:] in ALLOWED_EXTENSIONS:
        if not stem:
            stem = secure_filename(Path(fallback).stem) or "url_video"
        return f"{stem}{guessed_ext}"

    fallback_stem = stem or secure_filename(Path(fallback).stem) or "url_video"
    return _safe_video_filename(fallback, fallback_stem=fallback_stem)


def _is_disallowed_ip(ip_obj: "ipaddress._BaseAddress") -> bool:
    """判断 IP 是否属于内网/保留/回环/链路本地等禁止访问的范围。"""
    return bool(
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _assert_url_not_internal(raw_url: str) -> None:
    """SSRF 防护：解析主机名的所有 IP，拒绝指向内网/保留地址的请求。

    在实际连接前对域名做 DNS 解析并逐个校验，覆盖直接传入内网地址、
    以及域名解析到内网地址（含部分 DNS rebinding）两类情况。
    """
    if URL_IMPORT_ALLOW_PRIVATE_HOSTS:
        return

    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("仅支持 http/https 视频链接")

    hostname = (parsed.hostname or "").strip()
    if not hostname:
        raise ValueError("无法解析链接主机名")

    # 主机本身就是 IP 字面量时直接校验
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if _is_disallowed_ip(literal_ip):
            raise ValueError("出于安全考虑，禁止访问内网或保留地址")
        return

    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"无法解析链接主机名：{hostname}") from exc

    resolved_ips = {info[4][0] for info in addr_infos if info and info[4]}
    if not resolved_ips:
        raise ValueError(f"无法解析链接主机名：{hostname}")

    for ip_text in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if _is_disallowed_ip(ip_obj):
            raise ValueError("出于安全考虑，禁止访问内网或保留地址")


class _SSRFGuardRedirectHandler(HTTPRedirectHandler):
    """跟随重定向前校验目标地址，防止经由 3xx 跳转绕过 SSRF 检查。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _assert_url_not_internal(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ssrf_safe_opener = build_opener(_SSRFGuardRedirectHandler())


def _looks_like_html_payload(prefix: bytes) -> bool:
    snippet = bytes(prefix or b"").lstrip().lower()[:180]
    if not snippet:
        return False
    return (
        snippet.startswith(b"<!doctype html")
        or snippet.startswith(b"<html")
        or b"<html" in snippet
        or snippet.startswith(b"<?xml")
    )


def _download_video_with_http(
    raw_url: str, target_path: Path, max_bytes: int
) -> Tuple[Path, Dict[str, Any]]:
    _assert_url_not_internal(raw_url)
    request_obj = Request(
        raw_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )

    resolved_path = target_path
    try:
        with _ssrf_safe_opener.open(request_obj, timeout=45) as resp:
            content_type = str(resp.headers.get("Content-Type", "")).strip()
            content_disposition = str(resp.headers.get("Content-Disposition", "")).strip()
            if "text/html" in content_type.lower():
                raise RuntimeError("链接返回的是网页内容，请提供视频直链")

            guessed_name = _guess_video_filename_from_url(
                raw_url,
                content_disposition=content_disposition,
                content_type=content_type,
                fallback=target_path.name,
            )
            resolved_path = target_path.with_name(
                _safe_video_filename(guessed_name, fallback_stem=target_path.stem)
            )

            first_chunk = b""
            total_bytes = 0
            with open(resolved_path, "wb") as output_file:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    if not first_chunk:
                        first_chunk = chunk[:256]
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise ValueError(
                            f"远程视频大小超过限制（>{max_bytes / (1024 * 1024):.1f}MB）"
                        )
                    output_file.write(chunk)

            if total_bytes <= 0:
                raise RuntimeError("未获取到可用的视频内容")
            if _looks_like_html_payload(first_chunk):
                raise RuntimeError("链接返回的是网页内容，请确认视频链接有效")

            return resolved_path, {
                "download_source": "http_direct",
                "content_type": content_type,
                "bytes": total_bytes,
            }
    except HTTPError as exc:
        raise RuntimeError(f"链接下载失败（HTTP {exc.code}）") from exc
    except URLError as exc:
        reason = str(getattr(exc, "reason", "") or exc)
        raise RuntimeError(f"链接下载失败：{reason}") from exc
    except Exception:
        _safe_remove_file(resolved_path)
        raise


def _download_video_with_yt_dlp(
    raw_url: str, target_path: Path, max_bytes: int
) -> Tuple[Path, Dict[str, Any]]:
    try:
        import yt_dlp  # type: ignore
    except Exception as exc:
        raise RuntimeError("未检测到 yt-dlp，无法解析平台视频页链接") from exc

    target_stem = target_path.with_suffix("")
    outtmpl = str(target_stem) + ".%(ext)s"
    base_headers: Dict[str, str] = {
        "Referer": raw_url,
    }
    if SCRAPE_USER_AGENT:
        base_headers["User-Agent"] = SCRAPE_USER_AGENT

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "mp4/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "socket_timeout": 45,
        "http_headers": base_headers,
    }
    cookie_sources = _build_yt_dlp_cookie_sources(raw_url)
    source_errors: List[str] = []

    def _cleanup_temp_files() -> None:
        for path in target_stem.parent.glob(f"{target_stem.name}.*"):
            resolved = path.resolve(strict=False)
            if not resolved.exists() or not resolved.is_file():
                continue
            suffix = resolved.suffix.lower()
            if suffix in {".part", ".ytdl", ".tmp", ".temp"}:
                _safe_remove_file(resolved)

    for cookie_source in cookie_sources:
        ydl_opts = dict(base_opts)
        source_label = str(cookie_source.get("label", "no_cookies")).strip() or "no_cookies"
        cookie_file = str(cookie_source.get("cookiefile", "")).strip()
        browser_tuple = cookie_source.get("cookiesfrombrowser")
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        if browser_tuple:
            ydl_opts["cookiesfrombrowser"] = browser_tuple

        info: Dict[str, Any] = {}
        candidate_paths: List[Path] = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                raw_info = ydl.extract_info(raw_url, download=True)
                if isinstance(raw_info, dict):
                    info = raw_info
                    requested_downloads = raw_info.get("requested_downloads")
                    if isinstance(requested_downloads, list):
                        for item in requested_downloads:
                            if not isinstance(item, dict):
                                continue
                            filepath = str(
                                item.get("filepath") or item.get("_filename") or ""
                            ).strip()
                            if filepath:
                                candidate_paths.append(Path(filepath))
                    for key in ("filepath", "_filename"):
                        filepath = str(raw_info.get(key) or "").strip()
                        if filepath:
                            candidate_paths.append(Path(filepath))
                    prepared = str(ydl.prepare_filename(raw_info) or "").strip()
                    if prepared:
                        candidate_paths.append(Path(prepared))

            downloaded_path: Path | None = None
            for path in candidate_paths:
                resolved = path.resolve(strict=False)
                if resolved.exists() and resolved.is_file():
                    downloaded_path = resolved
                    break

            if downloaded_path is None:
                for path in target_stem.parent.glob(f"{target_stem.name}.*"):
                    resolved = path.resolve(strict=False)
                    if resolved.exists() and resolved.is_file():
                        downloaded_path = resolved
                        break

            if downloaded_path is None:
                raise RuntimeError("yt-dlp 下载完成但未找到输出文件")

            final_name = _safe_video_filename(downloaded_path.name, fallback_stem=target_path.stem)
            final_path = target_path.with_name(final_name)
            if downloaded_path.resolve(strict=False) != final_path.resolve(strict=False):
                _safe_remove_file(final_path)
                shutil.move(str(downloaded_path), str(final_path))

            file_size = final_path.stat().st_size if final_path.exists() else 0
            if file_size <= 0:
                _safe_remove_file(final_path)
                raise RuntimeError("yt-dlp 下载结果为空")
            if file_size > max_bytes:
                _safe_remove_file(final_path)
                raise ValueError(f"远程视频大小超过限制（>{max_bytes / (1024 * 1024):.1f}MB）")

            return final_path, {
                "download_source": "yt_dlp",
                "yt_dlp_cookie_source": source_label,
                "bytes": file_size,
                "title": str(info.get("title", "")).strip(),
                "extractor": str(info.get("extractor", "")).strip(),
                "video_id": str(info.get("id", "")).strip(),
                "webpage_url": str(info.get("webpage_url", "")).strip(),
                "original_url": str(info.get("original_url", "")).strip(),
            }
        except Exception as exc:
            source_errors.append(f"{source_label}: {str(exc)}")
            logger.info("yt-dlp 下载失败（%s）: %s", source_label, exc)
            _cleanup_temp_files()

    detail = "；".join(source_errors[:6]).strip()
    if len(source_errors) > 6:
        detail = f"{detail}；...共{len(source_errors)}项"
    if not detail:
        detail = "未知错误"
    raise RuntimeError(f"yt-dlp 下载失败：{detail}")


def _download_video_from_url(
    raw_url: Any,
    target_path: Path,
) -> Tuple[Path, Dict[str, Any]]:
    normalized_url = _normalize_source_url(raw_url)
    _assert_url_not_internal(normalized_url)
    url_candidates = _build_source_url_candidates(normalized_url)
    max_bytes = _safe_int(app.config.get("MAX_CONTENT_LENGTH"), 500 * 1024 * 1024, 1)
    errors: List[str] = []
    scraped_info: Dict[str, Any] = {}
    challenge_detected = False
    challenge_signals: List[str] = []

    platform_name = PLATFORM_LINK_DOWNLOADER.detect_platform(normalized_url)
    if platform_name:
        try:
            platform_result = PLATFORM_LINK_DOWNLOADER.maybe_download(
                normalized_url,
                target_path,
                max_bytes=max_bytes,
            )
            if platform_result is not None:
                downloaded_path, platform_meta = platform_result
                normalized_meta = dict(platform_meta or {})
                normalized_meta.setdefault("source_url", normalized_url)
                normalized_meta.setdefault("resolved_source_url", normalized_url)
                normalized_meta.setdefault("expected_media_ids", _extract_media_ids_from_url(normalized_url)[:8])
                normalized_meta.setdefault("candidate_batch", "platform_llm_downloader")
                return downloaded_path, normalized_meta
        except Exception as exc:
            errors.append(
                f"platform<{_compact_text(normalized_url, 120)}>: {_compact_text(str(exc), 220)}"
            )
            logger.info(
                "URL 下载：平台下载器失败，回退通用链路（%s / %s）: %s",
                platform_name,
                normalized_url,
                exc,
            )

    try:
        scraped_info = _scrape_page_info_with_scrapling(normalized_url)
        if isinstance(scraped_info, dict):
            base_url = str(scraped_info.get("final_url", "")).strip() or normalized_url
            _append_unique_url_candidate(
                url_candidates, scraped_info.get("final_url", ""), base_url=base_url
            )
            _append_unique_url_candidate(
                url_candidates, scraped_info.get("canonical_url", ""), base_url=base_url
            )
            for found_url in scraped_info.get("discovered_urls", []):
                _append_unique_url_candidate(url_candidates, found_url, base_url=base_url)
            for media_id in scraped_info.get("media_ids", []):
                media_id_text = _extract_numeric_media_id(media_id)
                if not media_id_text:
                    continue
                _append_unique_url_candidate(
                    url_candidates, f"https://www.douyin.com/video/{media_id_text}"
                )
                _append_unique_url_candidate(
                    url_candidates, f"https://www.iesdouyin.com/share/video/{media_id_text}/"
                )
            challenge_detected = bool(scraped_info.get("challenge_detected", False))
            challenge_signals = [
                str(item or "").strip()
                for item in (scraped_info.get("challenge_signals", []) or [])
                if str(item or "").strip()
            ]
            logger.info(
                "URL 页面抓取（scrapling）成功：%s，补充候选 %s 条",
                normalized_url,
                max(0, len(url_candidates) - 1),
            )
            if challenge_detected:
                logger.warning(
                    "URL 页面疑似触发验证（%s）: %s",
                    normalized_url,
                    ", ".join(challenge_signals) or "unknown",
                )
    except Exception as exc:
        logger.info("URL 页面抓取（scrapling）失败（%s）: %s", normalized_url, exc)
        errors.append(f"scrapling<{_compact_text(normalized_url, 120)}>: {_compact_text(str(exc), 220)}")

    source_host = str(urlparse(normalized_url).netloc or "").lower()
    expected_media_ids = _extract_media_ids_from_url(normalized_url)
    is_douyin_source = "douyin.com" in source_host or "iesdouyin.com" in source_host
    strict_media_scope = bool(
        SCRAPE_STRICT_MEDIA_ID_MATCH and is_douyin_source and expected_media_ids
    )

    def _candidate_matches_expected_media(candidate_url: str) -> bool:
        if not expected_media_ids:
            return False
        return any(_url_contains_media_id(candidate_url, media_id) for media_id in expected_media_ids)

    if expected_media_ids and is_douyin_source:
        for media_id in expected_media_ids:
            _append_unique_url_candidate(url_candidates, f"https://www.douyin.com/video/{media_id}")
            _append_unique_url_candidate(
                url_candidates, f"https://www.iesdouyin.com/share/video/{media_id}/"
            )

    ordered_candidates: List[str] = []

    def _push_candidate(url_text: str) -> None:
        text = str(url_text or "").strip()
        if text and text not in ordered_candidates:
            ordered_candidates.append(text)

    for media_id in expected_media_ids:
        _push_candidate(f"https://www.douyin.com/video/{media_id}")
        _push_candidate(f"https://www.iesdouyin.com/share/video/{media_id}/")

    for candidate in url_candidates:
        if _candidate_matches_expected_media(str(candidate)):
            _push_candidate(str(candidate))
    for candidate in url_candidates:
        _push_candidate(str(candidate))
    url_candidates = ordered_candidates[:32]

    strict_candidates = [
        item for item in url_candidates if _candidate_matches_expected_media(str(item))
    ]
    if strict_media_scope and not strict_candidates:
        raise RuntimeError("链接解析失败：未找到与原始视频 ID 匹配的候选地址")

    if strict_media_scope and strict_candidates:
        candidate_batches: List[Tuple[str, List[str]]] = [("strict_media_id", strict_candidates[:24])]
    else:
        direct_stream_candidates = [
            item
            for item in url_candidates
            if re.search(r"\.(mp4|m3u8|mov|webm)(?:$|[?#])", str(item).lower())
        ]
        page_candidates = [item for item in url_candidates if item not in direct_stream_candidates]
        candidate_batches = [("normal", (direct_stream_candidates + page_candidates)[:32])]

    def _record_error(method: str, candidate_url: str, exc_obj: Exception) -> None:
        short_url = _compact_text(candidate_url, 120)
        short_err = _compact_text(str(exc_obj), 220)
        errors.append(f"{method}<{short_url}>: {short_err}")

    def _attach_common_meta(meta: Dict[str, Any], candidate_url: str, batch_name: str) -> Dict[str, Any]:
        normalized_meta = dict(meta or {})
        normalized_meta["source_url"] = normalized_url
        normalized_meta["resolved_source_url"] = candidate_url
        normalized_meta["expected_media_ids"] = expected_media_ids[:8]
        normalized_meta["candidate_batch"] = batch_name
        if isinstance(scraped_info, dict):
            normalized_meta["scraped_final_url"] = str(scraped_info.get("final_url", "")).strip()
            normalized_meta["scraped_canonical_url"] = str(
                scraped_info.get("canonical_url", "")
            ).strip()
            normalized_meta["scraped_page_title"] = str(scraped_info.get("page_title", "")).strip()
            normalized_meta["scrape_fetch_method"] = str(scraped_info.get("fetch_method", "")).strip()
            normalized_meta["scrape_challenge_detected"] = bool(
                scraped_info.get("challenge_detected", False)
            )
            normalized_meta["scrape_challenge_signals"] = challenge_signals[:8]
        return normalized_meta

    def _extract_resolved_media_ids(meta: Dict[str, Any], candidate_url: str) -> List[str]:
        ids: List[str] = []
        if not isinstance(meta, dict):
            meta = {}
        video_id = _extract_numeric_media_id(meta.get("video_id"))
        if video_id and video_id not in ids:
            ids.append(video_id)
        for key in ("webpage_url", "original_url"):
            for media_id in _extract_media_ids_from_url(meta.get(key)):
                if media_id not in ids:
                    ids.append(media_id)
        for media_id in _extract_media_ids_from_url(candidate_url):
            if media_id not in ids:
                ids.append(media_id)
        return ids[:8]

    def _mismatch_error_text(actual_ids: List[str]) -> str:
        expected_text = ",".join(expected_media_ids[:4])
        actual_text = ",".join(actual_ids[:4]) if actual_ids else "unknown"
        return f"提取视频 ID 不匹配，期望 {expected_text}，实际 {actual_text}"

    for batch_name, batch_candidates in candidate_batches:
        for candidate_url in batch_candidates:
            try:
                downloaded_path, meta = _download_video_with_yt_dlp(
                    candidate_url, target_path, max_bytes
                )
                if not isinstance(meta, dict):
                    meta = {}
                if strict_media_scope:
                    actual_media_ids = _extract_resolved_media_ids(meta, candidate_url)
                    if actual_media_ids and not any(
                        item in expected_media_ids for item in actual_media_ids
                    ):
                        _safe_remove_file(downloaded_path)
                        raise RuntimeError(_mismatch_error_text(actual_media_ids))
                return downloaded_path, _attach_common_meta(meta, candidate_url, batch_name)
            except Exception as exc:
                _record_error("yt-dlp", candidate_url, exc)
                logger.info("URL 下载：yt-dlp 失败（%s）: %s", candidate_url, exc)

            if strict_media_scope:
                _record_error("http", candidate_url, RuntimeError("严格 ID 模式已禁用 HTTP 直链回退"))
                continue

            if strict_media_scope and not _candidate_matches_expected_media(candidate_url):
                _record_error("http", candidate_url, RuntimeError("严格 ID 模式已跳过非目标候选"))
                continue

            try:
                downloaded_path, meta = _download_video_with_http(
                    candidate_url, target_path, max_bytes
                )
                if not isinstance(meta, dict):
                    meta = {}
                if strict_media_scope:
                    actual_media_ids = _extract_resolved_media_ids(meta, candidate_url)
                    if actual_media_ids and not any(
                        item in expected_media_ids for item in actual_media_ids
                    ):
                        _safe_remove_file(downloaded_path)
                        raise RuntimeError(_mismatch_error_text(actual_media_ids))
                return downloaded_path, _attach_common_meta(meta, candidate_url, batch_name)
            except Exception as exc:
                _record_error("http", candidate_url, exc)
                logger.info("URL 下载：HTTP 直链失败（%s）: %s", candidate_url, exc)

    detail_items = [item for item in errors if str(item or "").strip()]
    detail = "；".join(detail_items[:6]).strip()
    if len(detail_items) > 6:
        detail = f"{detail}；...共{len(detail_items)}项错误"
    if not detail:
        detail = "未获取到可用的视频流"
    challenge_hint = ""
    if challenge_detected:
        challenge_tag = "、".join(challenge_signals[:4]).strip() or "未知验证类型"
        challenge_hint = (
            " 当前页面疑似触发人机验证，"
            f"标记：{challenge_tag}。请先在浏览器完成验证，或配置可用 cookies/proxy 后重试。"
        )
    raise RuntimeError(
        f"链接下载失败：{detail}。如为平台播放页链接，请安装并更新 yt-dlp 后重试。{challenge_hint}"
    )



def _resolve_batch_analyze_workers(
    *,
    total_files: int,
) -> int:
    workers = _safe_int(
        _env_text(("BATCH_ANALYZE_MAX_WORKERS", "batch_analyze_max_workers"), str(BATCH_ANALYZE_MAX_WORKERS)),
        BATCH_ANALYZE_MAX_WORKERS,
        1,
        16,
    )
    cpu_cap = max(1, int(os.cpu_count() or 1))
    file_cap = max(1, int(total_files or 1))
    return max(1, min(workers, cpu_cap, file_cap))



risk_blocklist_service = RiskBlocklistService(
    blocklist_path=RISK_BLOCKLIST_PATH,
    lock_obj=risk_blocklist_lock,
    logger_obj=logger,
)


def _normalize_sha256_fingerprint(value: Any) -> str:
    return risk_blocklist_service.normalize_sha256_fingerprint(value)


def _compute_file_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    return risk_blocklist_service.compute_file_sha256(file_path, chunk_size=chunk_size)


def _normalize_risk_blocklist_entry(raw_entry: Any) -> Dict[str, Any] | None:
    return risk_blocklist_service.normalize_entry(raw_entry)


def _load_risk_blocklist_unlocked() -> Dict[str, Dict[str, Any]]:
    return risk_blocklist_service.load_unlocked()


def _write_risk_blocklist_unlocked(entries: Dict[str, Dict[str, Any]]) -> None:
    risk_blocklist_service.write_unlocked(entries)


def _build_blacklist_match_risk(fingerprint: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    return risk_blocklist_service.build_match_risk(fingerprint, entry)


def _match_blacklisted_video_fingerprint_by_hash(
    fingerprint: str, source: str
) -> Dict[str, Any] | None:
    return risk_blocklist_service.match_fingerprint(fingerprint, source)


def _match_blacklisted_video_fingerprint(video_path: Path, source: str) -> Dict[str, Any] | None:
    return risk_blocklist_service.match_video_fingerprint(video_path, source)


def _register_blocked_video_fingerprint_by_hash(
    fingerprint: str, risk: Dict[str, Any], source: str
) -> str:
    return risk_blocklist_service.register_blocked_fingerprint(fingerprint, risk, source)


def _register_blocked_video_fingerprint(
    video_path: Path, risk: Dict[str, Any], source: str
) -> str:
    return risk_blocklist_service.register_blocked_video_fingerprint(video_path, risk, source)



risk_result_cache_service = RiskResultCacheService(
    cache_path=RISK_RESULT_CACHE_PATH,
    lock_obj=risk_result_cache_lock,
    ttl_seconds=RISK_RESULT_CACHE_TTL_SECONDS,
    max_entries=RISK_RESULT_CACHE_MAX_ENTRIES,
    logger_obj=logger,
)


def _build_upload_risk_model_cache_key(model_name: str, model_base_url: str) -> str:
    return risk_result_cache_service.build_model_key(model_name, model_base_url)


def _build_upload_risk_model_cache_key_from_agent(risk_agent: VideoAnalyzerAgent) -> str:
    return risk_result_cache_service.build_model_key_from_agent(risk_agent)


def _get_cached_upload_risk_result(fingerprint: str, model_key: str) -> Dict[str, Any] | None:
    return risk_result_cache_service.get(fingerprint, model_key)


def _set_cached_upload_risk_result(fingerprint: str, model_key: str, risk: Dict[str, Any]) -> None:
    risk_result_cache_service.set(fingerprint, model_key, risk)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _json_payload() -> Dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _extract_request_id(message: str) -> str:
    match = re.search(
        r"request[_\s-]*id['\"]?\s*[:]\s*['\"]?([A-Za-z0-9._-]+)",
        str(message or ""),
        flags=re.IGNORECASE,
    )
    return str(match.group(1)).strip() if match else ""


def _extract_http_status_code(message: str) -> int | None:
    text = str(message or "")
    patterns = (
        r"(?:error\s*code|status\s*code|http(?:\s*status)?)\s*[:=]?\s*(\d{3})",
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


def _normalize_provider_error(error: Any, default_status: int = 500) -> Tuple[str, int, bool]:
    if isinstance(error, ProviderFeatureUnsupportedError):
        capability = getattr(error.capability, "value", str(error.capability))
        hint = f" {error.hint}" if error.hint else ""
        return (
            f"当前模型平台 {error.provider} 不支持能力 {capability}，"
            f"请切换模型或关闭相应选项后重试。{hint} | code=provider_feature_unsupported",
            400,
            True,
        )

    raw_message = str(error or "").strip() or "模型服务调用失败"
    lower = raw_message.lower()
    request_id = _extract_request_id(raw_message)
    request_id_text = f"（请求 ID：{request_id}）" if request_id else ""

    is_web_search_not_open = (
        "toolnotopen" in lower or "web search" in lower or "联网搜索" in raw_message
    )
    if is_web_search_not_open:
        return (
            f"联网搜索功能未开通。请先开通后重试：{WEB_SEARCH_ACTIVATION_URL}{request_id_text}",
            400,
            True,
        )

    is_auth_error = (
        "authentication fails" in lower
        or "authentication_error" in lower
        or "invalid_api_key" in lower
        or "incorrect api key provided" in lower
        or "api key format is incorrect" in lower
        or ("api key" in lower and ("invalid" in lower or "is invalid" in lower or "无效" in raw_message))
    )
    if is_auth_error:
        return (
            f"模型鉴权失败：API Key 无效、已过期，或与当前平台/Base URL 不匹配。{request_id_text}",
            401,
            True,
        )

    if "invalidendpointormodel.notfound" in lower or (
        "model or endpoint" in lower and "not found" in lower
    ):
        return (
            f"模型连接失败：模型或接口不存在，请检查 Base URL 和模型名称。{request_id_text}",
            400,
            True,
        )

    if "does not exist or you do not have access" in lower:
        return (
            f"模型连接失败：模型不存在或当前账号无访问权限。{request_id_text}",
            403,
            True,
        )

    if "rate limit" in lower or "too many requests" in lower:
        return (f"请求过于频繁，请稍后重试。{request_id_text}", 429, True)

    if "timeout" in lower or "timed out" in lower:
        return (f"模型服务请求超时，请稍后重试。{request_id_text}", 504, True)

    status_code = _extract_http_status_code(raw_message)
    if status_code is not None and 400 <= status_code <= 599:
        return (f"模型服务调用失败（HTTP {status_code}）。{request_id_text}", status_code, True)

    return raw_message, default_status, False




history_service = HistoryService(
    history_path=HISTORY_PATH,
    lock_obj=history_lock,
    max_history=MAX_HISTORY,
    owner_pattern=HISTORY_OWNER_PATTERN,
    owner_max_len=HISTORY_OWNER_MAX_LEN,
    owner_header=HISTORY_OWNER_HEADER,
    owner_cookie=HISTORY_OWNER_COOKIE,
    owner_cookie_max_age=HISTORY_OWNER_COOKIE_MAX_AGE,
)


def _read_history_unlocked() -> List[Dict[str, Any]]:
    return history_service.read_unlocked()


def _write_history_unlocked(history: List[Dict[str, Any]]) -> None:
    history_service.write_unlocked(history)


def _normalize_history_owner(raw_owner: Any) -> str:
    return history_service.normalize_owner(raw_owner)


def _extract_history_owner() -> str:
    return history_service.extract_owner()


def _ensure_history_owner() -> str:
    return history_service.ensure_owner()


def _record_owner(record: Dict[str, Any]) -> str:
    return history_service.record_owner(record)


def _trim_history_per_owner(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return history_service.trim_history_per_owner(history)


def _strip_owner_field(record: Dict[str, Any]) -> Dict[str, Any]:
    return history_service.strip_owner_field(record)


def load_history(owner_id: str) -> List[Dict[str, Any]]:
    return history_service.load(owner_id)


def save_history(record: Dict[str, Any], owner_id: str) -> None:
    history_service.save(record, owner_id)


def delete_history_record(record_id: str, owner_id: str) -> None:
    history_service.delete(record_id, owner_id)


@app.after_request
def attach_history_owner_cookie(response):
    return history_service.attach_owner_cookie(response)



history_retention_cleanup_service = HistoryRetentionCleanupService(
    history_service_obj=history_service,
    output_root=OUTPUT_ROOT,
    ttl_seconds=HISTORY_RETENTION_TTL_SECONDS,
    scan_interval_seconds=HISTORY_RETENTION_SCAN_INTERVAL_SECONDS,
    logger_obj=logger,
)


def _start_history_retention_cleanup() -> None:
    history_retention_cleanup_service.start()


@app.before_request
def ensure_upload_video_auto_cleanup():
    _start_upload_video_auto_cleanup()
    _start_history_retention_cleanup()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _maybe_correct_subtitles(agent, srt_path, report=None) -> int:
    """Optionally run the LLM homophone-correction pass on a generated SRT.

    Gated by ``SUBTITLE_LLM_CORRECT`` (default off) so it never adds latency or
    token cost unless explicitly enabled. Never raises: a failed correction
    leaves the original subtitles untouched.
    """
    raw = str(os.getenv("SUBTITLE_LLM_CORRECT", "1")).strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return 0
    try:
        if report:
            report("subtitle", "正在用 AI 校对字幕同音字...")
        return _run_async(agent.correct_subtitles_with_llm(srt_path))
    except Exception as exc:  # noqa: BLE001 - correction is best-effort
        logger.warning("字幕 LLM 同音字纠错失败，保留原字幕: %s", exc)
        return 0



def _build_unique_upload_path(filename: str) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    candidate = UPLOAD_ROOT / safe_name
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while candidate.exists():
        candidate = UPLOAD_ROOT / f"{stem}_{counter}{suffix}"
        counter += 1

    return candidate



upload_session_service = UploadSessionService(
    session_root=UPLOAD_SESSION_ROOT,
    memory_buffers=upload_memory_buffers,
    memory_reserved_bytes=upload_memory_reserved_bytes,
    max_memory_total_bytes=UPLOAD_IN_MEMORY_MAX_TOTAL_BYTES,
    logger_obj=logger,
)


def _normalize_upload_id(raw_upload_id: Any) -> str:
    return upload_session_service.normalize_upload_id(raw_upload_id)


def _upload_session_json_path(upload_id: str) -> Path:
    return upload_session_service.session_json_path(upload_id)


def _upload_session_temp_path(upload_id: str) -> Path:
    return upload_session_service.session_temp_path(upload_id)


def _normalize_received_chunks(raw_chunks: Any, total_chunks: int) -> List[int]:
    return upload_session_service.normalize_received_chunks(raw_chunks, total_chunks)


def _load_upload_session(upload_id: str) -> Dict[str, Any] | None:
    return upload_session_service.load(upload_id)


def _save_upload_session(upload_id: str, session: Dict[str, Any]) -> None:
    upload_session_service.save(upload_id, session)


def _delete_upload_session(upload_id: str) -> None:
    global upload_memory_reserved_total_bytes
    upload_session_service.delete(upload_id)
    upload_memory_reserved_total_bytes = upload_session_service.reserved_total_bytes


def _reserve_upload_memory(upload_id: str, total_size: int) -> bool:
    global upload_memory_reserved_total_bytes
    reserved = upload_session_service.reserve_memory(upload_id, total_size)
    upload_memory_reserved_total_bytes = upload_session_service.reserved_total_bytes
    return reserved


def _release_upload_memory(upload_id: str) -> None:
    global upload_memory_reserved_total_bytes
    upload_session_service.release_memory(upload_id)
    upload_memory_reserved_total_bytes = upload_session_service.reserved_total_bytes


def _get_chunk_storage_mode(session: Dict[str, Any]) -> str:
    return upload_session_service.get_chunk_storage_mode(session)



upload_video_auto_cleanup_service = UploadVideoAutoCleanupService(
    upload_root=UPLOAD_ROOT,
    allowed_extensions=ALLOWED_EXTENSIONS,
    ttl_seconds=UPLOAD_VIDEO_AUTO_DELETE_TTL_SECONDS,
    scan_interval_seconds=UPLOAD_VIDEO_AUTO_DELETE_SCAN_INTERVAL_SECONDS,
    logger_obj=logger,
)


def _start_upload_video_auto_cleanup() -> None:
    upload_video_auto_cleanup_service.start()


def _mark_uploaded_video_loaded_now(video_path: Path) -> None:
    upload_video_auto_cleanup_service.mark_loaded_now(video_path)


def _create_unique_output_dir(video_path: Path) -> Path:
    base_name = secure_filename(video_path.stem) or "video"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = OUTPUT_ROOT / f"{base_name}_{timestamp}"
    counter = 1

    while candidate.exists():
        candidate = OUTPUT_ROOT / f"{base_name}_{timestamp}_{counter}"
        counter += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate



def _risk_decision_rank(decision: str) -> int:
    order = {"allow": 0, "restrict": 1, "block": 2}
    return order.get(str(decision or "").strip().lower(), 0)


def _risk_decision_from_rank(rank: int) -> str:
    if rank >= 2:
        return "block"
    if rank <= 0:
        return "allow"
    return "restrict"


def _risk_level_from_decision(decision: str) -> str:
    normalized = str(decision or "").strip().lower()
    if normalized == "block":
        return "high"
    if normalized == "restrict":
        return "medium"
    return "low"


def _resolve_risk_frame_count(max_frames: int, video_duration_seconds: float | None) -> int:
    base_count = _safe_int(max_frames, RISK_MAX_FRAMES, RISK_MIN_FRAMES, RISK_DYNAMIC_MAX_FRAMES)
    if video_duration_seconds is None or video_duration_seconds <= 0:
        return base_count

    growth_source = max(0.0, float(video_duration_seconds) - RISK_FRAME_GROWTH_START_SECONDS)
    bonus_frames = int(growth_source // RISK_FRAME_GROWTH_EVERY_SECONDS)
    return _safe_int(
        base_count + bonus_frames,
        base_count,
        RISK_MIN_FRAMES,
        RISK_DYNAMIC_MAX_FRAMES,
    )


def _stable_risk_sampling_seed(
    video_path: Path | None, video_duration_seconds: float | None, frame_count: int
) -> int:
    path_text = str(video_path or "")
    size = 0
    mtime_ns = 0
    if video_path is not None:
        try:
            stat_info = video_path.stat()
            size = int(getattr(stat_info, "st_size", 0))
            mtime_ns = int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1e9)))
        except OSError:
            pass
    duration_text = "none" if video_duration_seconds is None else f"{float(video_duration_seconds):.3f}"
    seed_text = f"{path_text}|{size}|{mtime_ns}|{duration_text}|{frame_count}"
    digest = hashlib.sha256(seed_text.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:16], 16)


def _build_risk_timestamps(
    max_frames: int,
    *,
    video_duration_seconds: float | None = None,
    video_path: Path | None = None,
) -> List[int]:
    frame_count = _resolve_risk_frame_count(max_frames, video_duration_seconds)
    if video_duration_seconds is None or video_duration_seconds <= 0:
        base = [0, 2, 5, 10, 15, 25, 35, 50, 70, 95, 125, 160, 200, 245, 295]
        return base[:frame_count]

    max_second = max(1, int(video_duration_seconds) - 1)
    seed = _stable_risk_sampling_seed(video_path, video_duration_seconds, frame_count)
    rng = random.Random(seed)

    timestamps: List[int] = []
    for idx in range(frame_count):
        segment_start = int((idx * max_second) / frame_count)
        segment_end = int(((idx + 1) * max_second) / frame_count)
        if idx == frame_count - 1:
            segment_end = max_second
        if segment_end < segment_start:
            segment_end = segment_start
        if segment_end == segment_start:
            sample = segment_start
        else:
            sample = rng.randint(segment_start, segment_end)
        timestamps.append(sample)

    unique_sorted = sorted(set(max(0, min(max_second, int(ts))) for ts in timestamps))
    while len(unique_sorted) < frame_count:
        candidate = rng.randint(0, max_second)
        if candidate in unique_sorted:
            continue
        unique_sorted.append(candidate)
        unique_sorted.sort()

    return unique_sorted[:frame_count]


def _is_image_input_not_supported_error(error: Any) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    image_tokens = ("image_url", "image input", "vision", "multimodal", "multi-modal")
    unsupported_tokens = (
        "not support",
        "unsupported",
        "only supported",
        "does not support",
        "invalid content type",
        "not allowed",
    )
    has_image_hint = any(token in text for token in image_tokens)
    has_unsupported_hint = any(token in text for token in unsupported_tokens)
    return has_image_hint and has_unsupported_hint


def _sample_risk_frames(
    agent: VideoAnalyzerAgent, video_path: Path, output_dir: Path, max_frames: int
) -> Tuple[List[Path], Path]:
    frame_dir = output_dir / ".risk_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: List[Path] = []
    video_duration_seconds = _probe_video_duration_seconds(
        video_path,
        str(getattr(agent, "ffmpeg_cmd", "")).strip() or "ffmpeg",
    )
    timestamps = _build_risk_timestamps(
        max_frames,
        video_duration_seconds=video_duration_seconds,
        video_path=video_path,
    )
    logger.info(
        "Risk gate sampling: duration=%.2fs, frames=%s, timestamps=%s",
        float(video_duration_seconds or 0.0),
        len(timestamps),
        timestamps,
    )
    for idx, second in enumerate(timestamps, start=1):
        frame_path = agent.generate_screenshot(video_path, frame_dir, second, step_num=idx)
        if frame_path is not None and frame_path.exists():
            frame_paths.append(frame_path)
    return frame_paths, frame_dir


def _build_env_visual_fallback_agent(primary_agent: VideoAnalyzerAgent) -> VideoAnalyzerAgent | None:
    api_key, model_name, model_base_url = _read_risk_fallback_env_model_options()
    if not api_key or not model_name:
        return None

    primary_api_key = str(getattr(primary_agent, "api_key", "")).strip()
    primary_model_name = str(getattr(primary_agent, "model", "")).strip()
    primary_base_url = str(getattr(primary_agent, "base_url", "")).strip()
    normalized_base_url = str(model_base_url or "").strip()

    # Skip meaningless self-fallback to the exact same visual model config.
    if (
        api_key == primary_api_key
        and model_name == primary_model_name
        and normalized_base_url == primary_base_url
    ):
        return None

    try:
        return VideoAnalyzerAgent(
            api_key=api_key,
            whisper_model="tiny",
            model_name=model_name,
            model_base_url=normalized_base_url,
        )
    except Exception as exc:
        logger.warning("系统级视觉风控兜底模型初始化失败: %s", exc)
        return None


def _try_env_visual_risk_fallback(
    primary_agent: VideoAnalyzerAgent, frame_paths: List[Path]
) -> Tuple[Dict[str, Any] | None, str]:
    env_agent = _build_env_visual_fallback_agent(primary_agent)
    if env_agent is None:
        return None, "ENV_VISUAL_FALLBACK_NOT_READY"

    try:
        raw = _run_async(_request_risk_decision(env_agent, frame_paths))
        normalized = _normalize_risk_result(
            raw if isinstance(raw, dict) else {}, frame_count=len(frame_paths)
        )
        normalized["fallback_mode"] = "env_visual_model_risk_gate"
        normalized["fallback_visual_model"] = str(getattr(env_agent, "model", "")).strip()
        normalized["fallback_visual_base_url"] = str(getattr(env_agent, "base_url", "")).strip()
        return normalized, ""
    except Exception as exc:
        error_message, status_code, _ = _normalize_provider_error(exc, default_status=500)
        return None, f"{error_message} (status={status_code})"


def _run_text_fallback_after_visual_unavailable(
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    reason_code: str,
    reason_suffix: str,
    provider_status: int | None = None,
    provider_error: str = "",
    env_visual_error: str = "",
    prefetched_text_risk: Dict[str, Any] | None = None,
    subtitle_cache_identity: str = "",
) -> Dict[str, Any]:
    fallback: Dict[str, Any]
    if isinstance(prefetched_text_risk, dict):
        fallback = dict(prefetched_text_risk)
        fallback.pop("fallback_non_strict", None)
        fallback["fallback_mode"] = "subtitle_keyword_risk_gate"

        prefetched_reason_code = str(fallback.get("reason_code", "")).strip().upper()
        prefetched_decision = str(fallback.get("decision", "")).strip().lower()
        if (
            prefetched_decision == "allow"
            and prefetched_reason_code == "TEXT_RISK_SIGNAL_INSUFFICIENT"
        ):
            existing_evidence = fallback.get("fallback_evidence", {})
            filename_used = (
                bool(existing_evidence.get("filename_used", False))
                if isinstance(existing_evidence, dict)
                else False
            )
            fallback.update(
                {
                    "decision": "block",
                    "risk_level": "high",
                    "reason_code": "TEXT_RISK_SIGNAL_INSUFFICIENT",
                    "reason": "视觉模型不支持图片输入，且字幕关键词信号不足，已按高风险默认拒绝上传。",
                    "confidence": 0.62,
                    "scores": {"nudity": 0.0, "violence": 0.0, "gore": 0.0},
                    "dimensions": {},
                    "frame_count": 0,
                    "fallback_mode": "subtitle_keyword_risk_gate",
                    "fallback_evidence": {
                        "subtitle_used": False,
                        "filename_used": filename_used,
                    },
                }
            )
    else:
        fallback = _run_text_fallback_risk_gate(
            agent,
            video_path,
            output_dir,
            subtitle_cache_identity=subtitle_cache_identity,
        )

    fallback["reason_code"] = str(fallback.get("reason_code", "")).strip() or reason_code
    base_reason = str(fallback.get("reason", "")).strip()
    if base_reason:
        fallback["reason"] = f"{base_reason}（{reason_suffix}）"
    else:
        fallback["reason"] = reason_suffix
    fallback["visual_fallback_attempted"] = True
    if provider_status is not None:
        fallback["provider_status"] = provider_status
    if provider_error:
        fallback["provider_error"] = provider_error
    if env_visual_error:
        fallback["fallback_visual_error"] = env_visual_error
    return fallback


def _apply_text_secondary_risk_gate_when_visual_available(
    primary_risk: Dict[str, Any],
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    text_risk: Dict[str, Any] | None = None,
    subtitle_cache_identity: str = "",
) -> Dict[str, Any]:
    merged = dict(primary_risk)
    if not isinstance(text_risk, dict):
        text_risk = _run_text_fallback_risk_gate(
            agent=agent,
            video_path=video_path,
            output_dir=output_dir,
            strict_on_insufficient_signal=False,
            fallback_mode="subtitle_keyword_secondary_gate",
            subtitle_cache_identity=subtitle_cache_identity,
        )

    primary_decision = str(merged.get("decision", "allow")).strip().lower()
    text_decision = str(text_risk.get("decision", "allow")).strip().lower()
    merged["text_fallback_applied"] = True
    merged["text_fallback_mode"] = "subtitle_keyword_secondary_gate"
    merged["text_fallback_risk"] = {
        "decision": text_decision,
        "risk_level": str(text_risk.get("risk_level", _risk_level_from_decision(text_decision))),
        "reason_code": str(text_risk.get("reason_code", "")),
        "reason": str(text_risk.get("reason", "")),
        "confidence": text_risk.get("confidence", 0.0),
    }

    if _risk_decision_rank(text_decision) <= _risk_decision_rank(primary_decision):
        merged["text_fallback_override"] = False
        return merged

    text_reason = str(text_risk.get("reason", "")).strip()
    merged["decision"] = text_decision
    merged["risk_level"] = str(text_risk.get("risk_level", "")).strip().lower() or _risk_level_from_decision(
        text_decision
    )
    merged["reason_code"] = str(text_risk.get("reason_code", "")).strip() or "TEXT_RISK_SECONDARY_GATE"
    merged["reason"] = (
        f"{text_reason}（视觉模型可用，字幕关键词兜底链路触发更严格策略）"
        if text_reason
        else "视觉模型可用，字幕关键词兜底链路触发更严格策略。"
    )
    merged["confidence"] = _normalize_risk_score(
        text_risk.get("confidence", merged.get("confidence", 0.6)),
        _normalize_risk_score(merged.get("confidence", 0.6), 0.6),
    )
    if isinstance(text_risk.get("scores"), dict):
        merged["scores"] = text_risk.get("scores", {})
    if isinstance(text_risk.get("dimensions"), dict):
        merged["dimensions"] = text_risk.get("dimensions", {})
    merged["text_fallback_override"] = True
    return merged


def _normalize_risk_result(raw_result: Dict[str, Any], frame_count: int) -> Dict[str, Any]:
    dimensions: Dict[str, Dict[str, Any]] = {}
    for key in ("nudity", "violence", "gore"):
        section = raw_result.get(key, {})
        if isinstance(section, dict):
            score = _normalize_risk_score(section.get("score", section.get("probability", 0.0)))
            label = str(section.get("label", "") or "").strip().lower()
            evidence = str(section.get("evidence", section.get("reason", "")) or "").strip()
        else:
            score = _normalize_risk_score(section, 0.0)
            label = ""
            evidence = ""
        dimensions[key] = {"score": score, "label": label, "evidence": evidence[:180]}

    scores = {key: dimensions[key]["score"] for key in dimensions}
    max_dimension = max(scores, key=scores.get) if scores else "nudity"
    max_score = scores.get(max_dimension, 0.0)
    has_explicit_or_severe_label = any(
        str(dimensions.get(key, {}).get("label", "")).lower() in {"explicit", "severe"}
        and float(dimensions.get(key, {}).get("score", 0.0)) >= 0.45
        for key in dimensions
    )
    has_hard_block_score = any(
        float(dimensions.get(key, {}).get("score", 0.0)) >= RISK_DIMENSION_HARD_BLOCK_SCORE
        for key in dimensions
    )
    has_critical_score = any(
        float(dimensions.get(key, {}).get("score", 0.0)) >= RISK_CRITICAL_SCORE
        for key in dimensions
    )
    model_reason_code = str(raw_result.get("reason_code", "") or "").strip().upper()
    has_hard_block_reason_code = model_reason_code in {
        "EXPLICIT_PORNOGRAPHIC_CONTENT",
        "SEVERE_VIOLENCE_CONTENT",
        "GORE_CONTENT",
        "SEXUAL_VIOLENCE_CONTENT",
    } or model_reason_code.endswith("_HIGH")
    has_hard_block_evidence = (
        has_explicit_or_severe_label
        or has_hard_block_score
        or has_critical_score
        or has_hard_block_reason_code
    )

    score_based_decision = "allow"
    if max_score >= RISK_BLOCK_THRESHOLD:
        score_based_decision = "block"
    elif max_score >= RISK_RESTRICT_THRESHOLD:
        score_based_decision = "restrict"
    if has_hard_block_evidence:
        score_based_decision = "block"

    decision = str(raw_result.get("decision", "") or "").strip().lower()
    if decision not in {"allow", "restrict", "block"}:
        decision = score_based_decision
    else:
        # Use the stricter result between model text decision and numeric evidence.
        decision = _risk_decision_from_rank(
            max(_risk_decision_rank(decision), _risk_decision_rank(score_based_decision))
        )

    confidence = _normalize_risk_score(raw_result.get("confidence", 0.6), 0.6)
    # Keep strict blocking when hard evidence exists; only mild low-confidence results may downgrade.
    if confidence < 0.35 and not has_hard_block_evidence:
        if decision == "restrict":
            decision = "allow"

    risk_level = str(raw_result.get("risk_level", "") or "").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        if decision == "block":
            risk_level = "high"
        elif decision == "restrict":
            risk_level = "medium"
        else:
            risk_level = "low"

    reason_code = str(raw_result.get("reason_code", "") or "").strip().upper()
    if not reason_code:
        if decision == "allow":
            reason_code = "SAFE_CONTENT"
        elif decision == "restrict":
            reason_code = f"{max_dimension.upper()}_MEDIUM"
        else:
            reason_code = f"{max_dimension.upper()}_HIGH"

    reason = str(raw_result.get("reason", "") or "").strip()
    if not reason:
        if decision == "allow":
            reason = "No high-risk nudity, violence, or gore was detected."
        elif decision == "restrict":
            reason = "Potentially sensitive content was detected."
        else:
            reason = "High-risk sensitive content was detected."

    return {
        "decision": decision,
        "risk_level": risk_level,
        "reason_code": reason_code,
        "reason": reason,
        "confidence": confidence,
        "scores": scores,
        "dimensions": dimensions,
        "frame_count": frame_count,
    }


async def _request_risk_decision(
    agent: VideoAnalyzerAgent, frame_paths: List[Path]
) -> Dict[str, Any]:
    prompt_schema = {
        "nudity": {"score": 0.0, "label": "none|mild|explicit", "evidence": ""},
        "violence": {"score": 0.0, "label": "none|mild|severe", "evidence": ""},
        "gore": {"score": 0.0, "label": "none|mild|severe", "evidence": ""},
        "decision": "allow|restrict|block",
        "risk_level": "low|medium|high",
        "confidence": 0.0,
        "reason_code": "UPPER_SNAKE_CASE",
        "reason": "short explanation",
    }
    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "You are a video safety moderator. "
                "Classify nudity, violence, and gore from the provided frames. "
                "Use block only when clear, explicit high-risk evidence exists. "
                "If uncertain, keep scores conservative and explain uncertainty. "
                f"Return JSON only with this schema: {json.dumps(prompt_schema, ensure_ascii=False)}"
            ),
        }
    ]

    for frame_path in frame_paths:
        with open(frame_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
            }
        )

    result = await agent._chat_completion_text(
        [
            {
                "role": "system",
                "content": "You are a content safety classifier for nudity, violence, and gore.",
            },
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
    )
    parsed = agent._parse_json_object_response(result)
    return parsed if isinstance(parsed, dict) else {}


def _run_video_risk_gate(
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    subtitle_cache_identity: str = "",
) -> Tuple[Dict[str, Any], Path]:
    frame_paths, frame_dir = _sample_risk_frames(
        agent=agent,
        video_path=video_path,
        output_dir=output_dir,
        max_frames=RISK_MAX_FRAMES,
    )
    if not frame_paths:
        logger.warning(
            "Risk gate frame extraction failed, fallback to subtitle keyword gate: %s",
            video_path,
        )
        fallback = _run_text_fallback_risk_gate(
            agent,
            video_path,
            output_dir,
            subtitle_cache_identity=subtitle_cache_identity,
        )
        fallback["reason_code"] = (
            str(fallback.get("reason_code", "")).strip() or "TEXT_RISK_FRAME_FALLBACK"
        )
        fallback["reason"] = (
            f"{str(fallback.get('reason', '')).strip()}（视觉帧提取失败，已自动启用字幕关键词风控兜底）"
        )
        fallback["frame_count"] = 0
        return fallback, frame_dir

    try:
        raw = _run_async(_request_risk_decision(agent, frame_paths))
        normalized = _normalize_risk_result(
            raw if isinstance(raw, dict) else {}, frame_count=len(frame_paths)
        )
        return normalized, frame_dir
    except Exception as exc:
        provider_status: int | None = None
        provider_error = ""
        reason_code = "TEXT_RISK_MODEL_FALLBACK"
        reason_suffix = (
            "视觉风控服务暂不可用，已优先尝试系统级视觉兜底模型，"
            "兜底模型不可用后自动启用字幕关键词风控兜底。"
        )

        if _is_image_input_not_supported_error(exc):
            logger.warning(
                "Risk gate model does not support image input, trying system env visual fallback first: %s",
                exc,
            )
            provider_error = str(exc or "").strip() or "visual_input_not_supported"
            reason_code = "TEXT_RISK_FALLBACK"
            reason_suffix = (
                "主视觉风控模型不支持图片输入，已优先尝试系统级视觉兜底模型，"
                "兜底模型不可用后自动启用字幕关键词风控兜底。"
            )
        else:
            error_message, status_code, _ = _normalize_provider_error(
                exc, default_status=500
            )
            provider_status = status_code
            provider_error = error_message
            logger.warning(
                "Risk gate visual check unavailable, trying system env visual fallback first: status=%s error=%s",
                status_code,
                error_message,
            )
            if status_code in {400, 401, 403}:
                reason_code = "TEXT_RISK_VISUAL_MODEL_UNAVAILABLE"
                reason_suffix = (
                    "主视觉风控模型当前不可用（鉴权/配置受限），已优先尝试系统级视觉兜底模型，"
                    "兜底模型不可用后自动启用字幕关键词风控兜底。"
                )

        env_visual_result, env_visual_error = _try_env_visual_risk_fallback(agent, frame_paths)
        if env_visual_result is not None:
            base_reason = str(env_visual_result.get("reason", "")).strip()
            env_visual_result["reason"] = (
                f"{base_reason}（主视觉风控不可用，已自动切换到系统级视觉兜底模型）"
                if base_reason
                else "主视觉风控不可用，已自动切换到系统级视觉兜底模型。"
            )
            env_visual_result["visual_fallback_attempted"] = True
            if provider_status is not None:
                env_visual_result["provider_status"] = provider_status
            if provider_error:
                env_visual_result["provider_error"] = provider_error
            return env_visual_result, frame_dir

        logger.warning(
            "System env visual fallback unavailable, switch to subtitle keyword risk fallback: %s",
            env_visual_error,
        )
        fallback = _run_text_fallback_after_visual_unavailable(
            agent=agent,
            video_path=video_path,
            output_dir=output_dir,
            reason_code=reason_code,
            reason_suffix=reason_suffix,
            provider_status=provider_status,
            provider_error=provider_error,
            env_visual_error=env_visual_error,
            subtitle_cache_identity=subtitle_cache_identity,
        )
        return fallback, frame_dir


def _reason_code_slug(reason_code: str) -> str:
    slug = secure_filename(str(reason_code or "").strip().lower()).replace("-", "_")
    return slug or "content_policy"


def _quarantine_upload_file(video_path: Path, reason_code: str) -> Path | None:
    try:
        resolved = video_path.resolve(strict=False)
        _assert_within(resolved, UPLOAD_ROOT, "filepath")
    except ValueError:
        return None

    if not resolved.exists() or not resolved.is_file():
        return None

    reason_dir = QUARANTINE_ROOT / _reason_code_slug(reason_code)
    reason_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = reason_dir / f"{resolved.stem}_{timestamp}{resolved.suffix}"
    counter = 1
    while target.exists():
        target = reason_dir / f"{resolved.stem}_{timestamp}_{counter}{resolved.suffix}"
        counter += 1

    try:
        shutil.move(str(resolved), str(target))
        return target
    except OSError as exc:
        logger.warning("Failed to quarantine blocked video: %s", exc)
        return None


def _should_block_by_risk(decision: str) -> bool:
    return decision == "block" or (decision == "restrict" and RISK_BLOCK_ON_RESTRICT)


def _build_upload_staging_path(filename: str) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name:
        safe_name = f"staging_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    suffix = Path(safe_name).suffix or ".mp4"
    stem = Path(safe_name).stem or "staging"
    candidate = UPLOAD_STAGING_ROOT / f"{stem}_{uuid4().hex[:10]}{suffix}"
    _assert_within(candidate.resolve(strict=False), UPLOAD_STAGING_ROOT, "staging_path")
    return candidate


def _safe_remove_file(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        logger.warning("删除文件失败: %s", path)


class UploadRiskService:
    def resolve_upload_risk_api_key(self) -> str:
        api_key, _, _ = _read_shared_backend_model_options(require_api_key=False)
        return str(api_key or "").strip()

    def upload_risk_unavailable_message(self) -> str:
        return (
            "上传风控服务不可用，已拒绝上传。"
            "请检查后端 .env 中的 MODEL_API_KEY / MODEL_NAME / MODEL_BASE_URL 配置后重试。"
        )

    def upload_risk_unavailable_payload(self) -> Dict[str, Any]:
        return {
            "error": self.upload_risk_unavailable_message(),
            "code": "risk_service_unavailable",
        }

    def build_risk_agent_for_upload(
        self, api_key: str = "", model_name: str = "", model_base_url: str = ""
    ) -> VideoAnalyzerAgent:
        # 上传风控与主分析共用同一套后端模型配置，前端入参不参与覆盖。
        shared_api_key, shared_model_name, shared_model_base_url = _read_shared_backend_model_options(
            require_api_key=True
        )
        risk_api_key = str(shared_api_key or "").strip()
        if not risk_api_key:
            raise ValueError("上传风控模型 API Key 未配置")

        risk_model_name = str(shared_model_name or "").strip()
        risk_model_base_url = str(shared_model_base_url or "").strip()
        return VideoAnalyzerAgent(
            api_key=risk_api_key,
            whisper_model="tiny",
            model_name=risk_model_name,
            model_base_url=risk_model_base_url,
        )

    def moderate_staged_upload(
        self,
        staged_video_path: Path,
        risk_agent: VideoAnalyzerAgent,
        file_fingerprint: str = "",
    ) -> Dict[str, Any]:
        output_dir = _create_unique_output_dir(staged_video_path)
        try:
            risk, _ = _run_video_risk_gate(
                risk_agent,
                staged_video_path,
                output_dir,
                subtitle_cache_identity=file_fingerprint,
            )
            return risk
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)

    def risk_reject_payload(self, risk: Dict[str, Any]) -> Dict[str, Any]:
        reason_code = str(risk.get("reason_code", "CONTENT_POLICY_VIOLATION")).strip()
        return {
            "error": CONTENT_POLICY_BLOCK_MESSAGE,
            "code": "content_policy_violation",
            "risk": {**risk, "reason_code": reason_code},
        }

    def is_risk_infra_failure(self, risk: Dict[str, Any]) -> bool:
        reason_code = str(risk.get("reason_code", "")).strip().upper()
        return reason_code in {
            "RISK_MODEL_AUTH_FAILED",
            "RISK_MODEL_CONFIG_INVALID",
            "RISK_MODEL_UNAVAILABLE",
            "RISK_FRAME_EXTRACTION_FAILED",
            "RISK_GATE_INTERNAL_ERROR",
        }

    def build_upload_risk_failure_response(self, risk: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        reason_code = str(risk.get("reason_code", "")).strip().upper()
        provider_error = str(risk.get("provider_error", "")).strip()
        request_id = _extract_request_id(provider_error)
        request_id_text = f"（请求 ID：{request_id}）" if request_id else ""
        if reason_code == "RISK_MODEL_AUTH_FAILED":
            auth_error = provider_error
            if not auth_error or "HTTP 401" in auth_error.upper():
                auth_error = (
                    "模型鉴权失败：API Key 无效、已过期，或与当前平台/Base URL 不匹配。"
                    f"{request_id_text}"
                )
            return (
                {
                    "error": auth_error,
                    "code": "risk_model_auth_failed",
                },
                401,
            )
        if reason_code == "RISK_MODEL_CONFIG_INVALID":
            config_error = provider_error
            has_specific_hint = (
                "模型连接失败：" in config_error
                or "模型鉴权失败：" in config_error
                or "模型服务请求超时" in config_error
                or "请求过于频繁" in config_error
            )
            if not has_specific_hint:
                config_error = (
                    "上传前模型配置校验失败：请检查模型接口 Base URL 与模型名称是否匹配当前平台，"
                    "并确认模型支持图片理解（风控检测依赖图片输入）。"
                    f"{request_id_text}"
                )
            return (
                {
                    "error": config_error,
                    "code": "risk_model_config_invalid",
                },
                400,
            )
        return self.upload_risk_unavailable_payload(), 503


upload_risk_service = UploadRiskService()


def _resolve_upload_risk_api_key() -> str:
    return upload_risk_service.resolve_upload_risk_api_key()


def _upload_risk_unavailable_message() -> str:
    return upload_risk_service.upload_risk_unavailable_message()


def _upload_risk_unavailable_payload() -> Dict[str, Any]:
    return upload_risk_service.upload_risk_unavailable_payload()


def _build_risk_agent_for_upload(
    api_key: str = "", model_name: str = "", model_base_url: str = ""
) -> VideoAnalyzerAgent:
    return upload_risk_service.build_risk_agent_for_upload(
        api_key=api_key,
        model_name=model_name,
        model_base_url=model_base_url,
    )


def _moderate_staged_upload(
    staged_video_path: Path,
    risk_agent: VideoAnalyzerAgent,
    file_fingerprint: str = "",
) -> Dict[str, Any]:
    return upload_risk_service.moderate_staged_upload(
        staged_video_path,
        risk_agent,
        file_fingerprint=file_fingerprint,
    )


def _risk_reject_payload(risk: Dict[str, Any]) -> Dict[str, Any]:
    return upload_risk_service.risk_reject_payload(risk)


def _is_risk_infra_failure(risk: Dict[str, Any]) -> bool:
    return upload_risk_service.is_risk_infra_failure(risk)


def _build_upload_risk_failure_response(risk: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    return upload_risk_service.build_upload_risk_failure_response(risk)


def _compute_video_fingerprint_safely(video_path: Path, source: str) -> str:
    try:
        return _compute_file_sha256(video_path)
    except OSError as exc:
        logger.warning("计算视频指纹失败（%s），将回退到非缓存路径: %s", source, exc)
        return ""


def _check_upload_blacklist_precheck(
    staged_video_path: Path,
    *,
    source: str,
    file_fingerprint: str = "",
) -> Tuple[Dict[str, Any] | None, str]:
    fingerprint = file_fingerprint or _compute_video_fingerprint_safely(staged_video_path, source)
    if fingerprint:
        blacklist_risk = _match_blacklisted_video_fingerprint_by_hash(fingerprint, source)
    else:
        blacklist_risk = _match_blacklisted_video_fingerprint(staged_video_path, source)
    if blacklist_risk is not None and fingerprint and not str(
        blacklist_risk.get("hash_sha256", "")
    ).strip():
        blacklist_risk["hash_sha256"] = fingerprint
    return blacklist_risk, fingerprint


def _build_deferred_upload_risk_result(fingerprint: str = "") -> Dict[str, Any]:
    risk: Dict[str, Any] = {
        "decision": "allow",
        "risk_level": "low",
        "reason_code": "UPLOAD_RISK_DEFERRED_TO_ANALYZE",
        "reason": "上传阶段仅执行轻量安全校验，内容风控已延后到分析前执行。",
        "confidence": 0.0,
        "scores": {"nudity": 0.0, "violence": 0.0, "gore": 0.0},
        "dimensions": {},
        "frame_count": 0,
        "deferred_to_analyze": True,
    }
    if fingerprint:
        risk["hash_sha256"] = fingerprint
    return risk


def _run_upload_pre_risk_check(
    staged_video_path: Path,
    risk_agent: VideoAnalyzerAgent | None,
    *,
    source: str,
    file_fingerprint: str = "",
    skip_blacklist: bool = False,
) -> Tuple[Dict[str, Any], str, str]:
    fingerprint = file_fingerprint or _compute_video_fingerprint_safely(staged_video_path, source)
    if not skip_blacklist:
        blacklist_risk, fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staged_video_path,
            source=source,
            file_fingerprint=fingerprint,
        )
        if blacklist_risk is not None:
            return blacklist_risk, fingerprint, "blacklist"

    cache_model_key = ""
    if risk_agent is not None:
        cache_model_key = _build_upload_risk_model_cache_key_from_agent(risk_agent)
    else:
        _, model_name, model_base_url = _read_shared_backend_model_options(require_api_key=False)
        cache_model_key = _build_upload_risk_model_cache_key(model_name, model_base_url)
    if fingerprint and cache_model_key:
        cached_risk = _get_cached_upload_risk_result(fingerprint, cache_model_key)
        if cached_risk is not None:
            logger.info(
                "上传前风控缓存命中: source=%s, sha256_prefix=%s",
                source,
                fingerprint[:12],
            )
            cached_risk["cache_hit"] = True
            cached_risk["cache_source"] = "upload_risk_precheck"
            if not str(cached_risk.get("hash_sha256", "")).strip():
                cached_risk["hash_sha256"] = fingerprint
            return cached_risk, fingerprint, "cache"

    return _build_deferred_upload_risk_result(fingerprint), fingerprint, "deferred"


def _read_shared_backend_model_options(require_api_key: bool = True) -> Tuple[str, str, str]:
    """
    统一读取后端模型参数（风控与分析共用同一模型配置）。
    仅管理员可通过 .env 修改，无需前端传参。
    """
    api_key = _env_text(
        (
            "MODEL_API_KEY",
            "ARK_API_KEY",
            "OPENAI_API_KEY",
            "LLM_API_KEY",
            "RISK_API_KEY",
            "RISK_FALLBACK_API_KEY",
        ),
        "",
    )
    model_name = _env_text(
        (
            "MODEL_NAME",
            "LLM_MODEL",
            "RISK_MODEL_NAME",
            "RISK_FALLBACK_MODEL_NAME",
        ),
        "",
    )
    model_base_url = _env_text(
        (
            "MODEL_BASE_URL",
            "LLM_BASE_URL",
            "RISK_MODEL_BASE_URL",
            "RISK_FALLBACK_MODEL_BASE_URL",
        ),
        "",
    )

    if require_api_key:
        missing: list[str] = []
        if not api_key:
            missing.append("MODEL_API_KEY（或 ARK_API_KEY / OPENAI_API_KEY）")
        if not model_name:
            missing.append("MODEL_NAME（需使用支持图片输入的视觉模型）")
        if not model_base_url:
            missing.append("MODEL_BASE_URL")
        if missing:
            raise ValueError(
                "后端模型未配置：请在 .env 中设置 " + "、".join(missing) + "。"
            )

    return (
        str(api_key or "").strip(),
        str(model_name or "").strip(),
        str(model_base_url or "").strip(),
    )


def _normalize_processing_options(data: Dict[str, Any]) -> Tuple[str, bool, bool, int, float]:
    # 仅后端 .env 生效（管理员可调），前端不再覆盖：
    # - WHISPER_MODE/WHISPER_MODEL: 字幕识别模型
    # - ANALYZE_USE_VIDEO/USE_VIDEO: 视频上传分析模式开关（默认开启）
    # - VIDEO_ANALYZE_FPS/ANALYZE_FPS/VIDEO_FPS: 视频模式抽帧频率
    env_whisper_model = (
        _env_text(("WHISPER_MODE", "WHISPER_MODEL", "whisper_mode"), "base")
        .strip()
        .lower()
        or "base"
    )
    if env_whisper_model not in ALLOWED_WHISPER_MODELS:
        env_whisper_model = "base"

    env_use_video = _env_bool(("ANALYZE_USE_VIDEO", "USE_VIDEO", "use_video"), True)
    env_fps = _safe_float(
        _env_text(("VIDEO_ANALYZE_FPS", "ANALYZE_FPS", "VIDEO_FPS", "fps"), "1.0"),
        1.0,
        FPS_MIN,
        FPS_MAX,
    )
    env_web_search = _env_bool(("WEB_SEARCH", "web_search"), False)
    env_max_vision = _safe_int(
        _env_text(("MAX_VISION", "max_vision"), "10"),
        10,
        0,
        MAX_VISION_CALLS,
    )

    raw_web_search = data.get("web_search")
    web_search = _as_bool(raw_web_search) if raw_web_search is not None else env_web_search
    raw_max_vision = data.get("max_vision")
    max_vision = (
        _safe_int(raw_max_vision, env_max_vision, 0, MAX_VISION_CALLS)
        if raw_max_vision not in (None, "")
        else env_max_vision
    )

    whisper_model = env_whisper_model
    use_video = env_use_video
    fps = env_fps
    return whisper_model, use_video, web_search, max_vision, fps


def _normalize_model_options(data: Dict[str, Any]) -> Tuple[str, str]:
    _ = data
    _, model_name, model_base_url = _read_shared_backend_model_options(require_api_key=False)
    return model_name, model_base_url


def _normalize_upload_model_options(
    data: Dict[str, Any],
    require_api_key: bool = False,
    require_model_name: bool = False,
) -> Tuple[str, str, str]:
    _ = data
    api_key, model_name, model_base_url = _read_shared_backend_model_options(
        require_api_key=require_api_key
    )
    if require_model_name and not model_name:
        raise ValueError("后端模型名称未配置，请在 .env 中设置 MODEL_NAME。")
    return api_key, model_name, model_base_url


def _compact_text(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max(1, int(limit)):
        return text
    return text[: max(1, int(limit) - 1)].rstrip() + "…"


def _extract_action_phrase_from_subtitle(text: Any) -> Tuple[str, str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return "", ""

    verbs = [
        "打开",
        "点击",
        "选择",
        "输入",
        "搜索",
        "切换",
        "进入",
        "创建",
        "新增",
        "删除",
        "修改",
        "编辑",
        "保存",
        "提交",
        "上传",
        "下载",
        "导出",
        "复制",
        "粘贴",
        "拖动",
        "调整",
        "设置",
        "勾选",
        "取消",
        "确认",
        "启动",
        "运行",
    ]
    for verb in verbs:
        idx = normalized.find(verb)
        if idx < 0:
            continue
        tail = normalized[idx + len(verb) :].strip()
        tail = re.split(r"[，。！？；,.!?;：:\n]", tail, maxsplit=1)[0].strip()
        tail = re.sub(r"^(了|一下|一下子|并|然后|再|再去|将|把|对|给|到|为|向|于|在|通过|进行|完成)\s*", "", tail)
        return verb, _compact_text(tail, 16)
    return "", ""


def _pick_timeline_points_from_subtitles(
    subtitles: List[Dict[str, Any]],
    minimum: int = 3,
) -> List[Dict[str, Any]]:
    valid_items = [
        item
        for item in subtitles
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    ]
    total = len(valid_items)
    if total <= 0:
        return []

    target = max(minimum, min(FALLBACK_CANDIDATE_MAX_STEPS, 5))
    target = min(target, total) if total >= minimum else total
    if target <= 0:
        return []

    segment = float(total) / float(max(1, target))
    selected_indices: List[int] = []
    for idx in range(target):
        center = int(idx * segment + segment / 2.0)
        selected_indices.append(max(0, min(total - 1, center)))
    selected_indices = sorted(set(selected_indices))

    timeline: List[Dict[str, Any]] = []
    for sub_idx in selected_indices:
        item = valid_items[sub_idx]
        start_seconds = _safe_float(item.get("start_seconds"), 0.0, 0.0)
        timeline.append(
            {
                "time": _format_seconds_to_mmss(start_seconds),
                "text": _compact_text(item.get("text", ""), 72),
                "start_seconds": start_seconds,
                "raw": item,
            }
        )
    return timeline


def _ensure_minimum_step_count(
    steps: List[Dict[str, Any]],
    *,
    min_steps: int = FALLBACK_MIN_STEPS,
    reason: str = "",
) -> List[Dict[str, Any]]:
    normalized_steps = list(steps)
    if len(normalized_steps) >= min_steps:
        return normalized_steps

    defaults = [
        ("00:00", "内容概览", "已自动补齐基础概览，帮助快速理解视频整体主题。"),
        ("00:20", "关键信息提炼", "已自动补齐关键要点，建议结合原视频进行确认。"),
        ("00:40", "下一步建议", "可切换更强模型或补充字幕后再次分析，以提升步骤准确率。"),
    ]
    reason_hint = _compact_text(reason, 54)
    while len(normalized_steps) < min_steps:
        idx = len(normalized_steps)
        default_time, default_title, default_desc = defaults[min(idx, len(defaults) - 1)]
        normalized_steps.append(
            {
                "step": idx + 1,
                "time": default_time,
                "title": default_title,
                "description": (
                    f"{default_desc}（{reason_hint}）" if reason_hint and idx == 1 else default_desc
                ),
                "confidence": round(max(0.2, 0.3 - idx * 0.03), 2),
                "source": "fallback_padding",
            }
        )
    return normalized_steps


def _build_subtitle_candidate_steps(
    subtitles: List[Dict[str, Any]],
    max_steps: int = FALLBACK_CANDIDATE_MAX_STEPS,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    timeline = _pick_timeline_points_from_subtitles(subtitles, minimum=FALLBACK_MIN_STEPS)
    if not timeline:
        return [], []

    if len(timeline) > max_steps:
        timeline = timeline[:max_steps]

    steps: List[Dict[str, Any]] = []
    for idx, point in enumerate(timeline, start=1):
        text = str(point.get("text", "")).strip()
        verb, obj = _extract_action_phrase_from_subtitle(text)
        if verb:
            action_title = f"{verb}{obj}" if obj else f"{verb}相关操作"
        else:
            action_title = _compact_text(text, 16) or f"候选步骤 {idx}"
        confidence = round(max(0.3, 0.52 - (idx - 1) * 0.06), 2)
        steps.append(
            {
                "step": idx,
                "time": str(point.get("time", "00:00")) or "00:00",
                "title": action_title,
                "description": (
                    f"{_compact_text(text, 120)}（自动从字幕提取“动作+对象+时间”，当前为低置信度候选）"
                ),
                "confidence": confidence,
                "source": "subtitle_candidate",
            }
        )
    return _ensure_minimum_step_count(steps), timeline


def _build_timeline_summary_steps(
    video_path: Path,
    subtitles: List[Dict[str, Any]],
    reason: str = "",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str, List[str]]:
    duration_seconds = _probe_video_duration_seconds(video_path)
    timeline_points: List[float]
    if duration_seconds is not None and duration_seconds > 3:
        timeline_points = [0.0, duration_seconds * 0.35, duration_seconds * 0.7, duration_seconds * 0.92]
    else:
        timeline_points = [0.0, 20.0, 40.0, 60.0]

    subtitle_timeline = _pick_timeline_points_from_subtitles(subtitles, minimum=FALLBACK_MIN_STEPS)
    timeline = subtitle_timeline
    if len(timeline) < FALLBACK_MIN_STEPS:
        timeline = [
            {
                "time": _format_seconds_to_mmss(point),
                "text": "",
                "start_seconds": point,
            }
            for point in timeline_points[:FALLBACK_MIN_STEPS]
        ]
    while len(timeline) < FALLBACK_MIN_STEPS:
        point = timeline_points[len(timeline)] if len(timeline) < len(timeline_points) else timeline_points[-1]
        timeline.append(
            {"time": _format_seconds_to_mmss(point), "text": "", "start_seconds": point}
        )

    title_seed = _compact_text(video_path.stem.replace("_", " ").replace("-", " "), 24) or "当前视频"
    reason_text = _compact_text(reason, 72)
    timeline_text = " / ".join(item.get("time", "00:00") for item in timeline[:FALLBACK_MIN_STEPS])
    key_points: List[str] = []
    for item in timeline[:5]:
        point_text = _compact_text(item.get("text", ""), 50)
        if point_text:
            key_points.append(f"{item.get('time', '00:00')}：{point_text}")
    while len(key_points) < 3:
        key_points.append(f"{timeline[min(len(key_points), len(timeline) - 1)].get('time', '00:00')}：待人工复核的关键片段")
    key_points = key_points[:5]

    summary_title = f"{title_seed} 视频时间线摘要"
    confidence_note = (
        "当前结果为摘要降级版：步骤结构置信度较低，系统优先保证可读内容输出。"
    )
    degrade_note = (
        f"未提炼出标准步骤，已切换为时间线摘要模式。{f' 原因：{reason_text}' if reason_text else ''}"
    )

    steps = [
        {
            "step": 1,
            "time": _format_seconds_to_mmss(timeline_points[0]),
            "title": "视频主题",
            "description": f"{summary_title}。系统已自动提炼可交付内容供快速查看。",
            "confidence": 0.32,
            "source": "timeline_summary",
        },
        {
            "step": 2,
            "time": _format_seconds_to_mmss(timeline_points[1]),
            "title": "关键时间点",
            "description": f"关键时间片段：{timeline_text}。建议优先查看这些位置。",
            "confidence": 0.3,
            "source": "timeline_summary",
        },
        {
            "step": 3,
            "time": _format_seconds_to_mmss(timeline_points[2]),
            "title": "主要内容摘要",
            "description": "；".join(key_points),
            "confidence": 0.28,
            "source": "timeline_summary",
        },
        {
            "step": 4,
            "time": _format_seconds_to_mmss(timeline_points[3]),
            "title": "下一步建议",
            "description": f"{confidence_note} {degrade_note}",
            "confidence": 0.26,
            "source": "timeline_summary",
        },
    ]
    return steps, timeline, summary_title, key_points


def _build_fallback_steps_when_empty(
    agent: VideoAnalyzerAgent,
    video_path: Path,
    output_dir: Path,
    srt_path: str | None,
    *,
    subtitle_cache_identity: str = "",
    reason: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str | None]:
    normalized_srt_path = str(srt_path or "").strip() or None
    subtitles: List[Dict[str, Any]] = []

    if normalized_srt_path and Path(normalized_srt_path).exists():
        try:
            subtitles = agent.parse_srt(normalized_srt_path)
        except Exception as exc:
            logger.warning("解析现有字幕失败，准备尝试重新生成字幕: %s", exc)
            subtitles = []

    if not subtitles:
        try:
            generated_srt = agent.generate_subtitles(
                str(video_path),
                str(output_dir),
                cache_identity=subtitle_cache_identity or None,
            )
            normalized_srt_path = generated_srt if generated_srt else normalized_srt_path
            if normalized_srt_path and Path(normalized_srt_path).exists():
                subtitles = agent.parse_srt(normalized_srt_path)
        except Exception as exc:
            logger.warning("降级步骤生成时重新转写字幕失败: %s", exc)
            subtitles = []

    subtitle_steps, subtitle_timeline = _build_subtitle_candidate_steps(subtitles)
    if subtitle_steps:
        summary_title = (
            _compact_text(video_path.stem.replace("_", " ").replace("-", " "), 24) or "当前视频"
        ) + " 候选步骤"
        key_points = [f"{item.get('time', '00:00')}：{_compact_text(item.get('title', ''), 24)}" for item in subtitle_steps[:5]]
        while len(key_points) < 3:
            key_points.append("00:00：待人工复核候选步骤")
        result_meta = {
            "result_mode": "candidate_steps",
            "analysis_note": "未识别到标准步骤，已自动生成候选步骤（低置信度）。",
            "degrade_reason": "standard_steps_not_detected_subtitle_candidates_generated",
            "content_title": summary_title,
            "key_points": key_points[:5],
            "timeline_points": subtitle_timeline[:5],
            "confidence_note": "候选步骤来自字幕启发式抽取，建议结合原视频确认。",
            "fallback_used": True,
        }
        return subtitle_steps, result_meta, normalized_srt_path

    summary_steps, timeline, summary_title, key_points = _build_timeline_summary_steps(
        video_path,
        subtitles,
        reason=reason,
    )
    result_meta = {
        "result_mode": "timeline_summary",
        "analysis_note": "未识别到标准步骤，已自动生成时间线摘要。",
        "degrade_reason": "subtitle_signal_insufficient_timeline_summary_generated",
        "content_title": summary_title,
        "key_points": key_points[:5],
        "timeline_points": timeline[:5],
        "confidence_note": "摘要模式用于保底输出，步骤细粒度较低。",
        "fallback_used": True,
    }
    return summary_steps, result_meta, normalized_srt_path


def _extract_timeline_from_steps(steps: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    for item in steps:
        if not isinstance(item, dict):
            continue
        time_text = str(item.get("time", "")).strip()
        title_text = _compact_text(item.get("title", ""), 40)
        if not time_text and not title_text:
            continue
        timeline.append({"time": time_text or "00:00", "text": title_text})
        if len(timeline) >= limit:
            break
    while len(timeline) < FALLBACK_MIN_STEPS:
        defaults = ["00:00", "00:20", "00:40"]
        timeline.append({"time": defaults[len(timeline)], "text": "待确认片段"})
    return timeline


def _build_key_points_from_steps(steps: List[Dict[str, Any]], limit: int = 5) -> List[str]:
    key_points: List[str] = []
    for item in steps:
        if not isinstance(item, dict):
            continue
        title_text = _compact_text(item.get("title", ""), 24)
        desc_text = _compact_text(item.get("description", ""), 48)
        time_text = str(item.get("time", "")).strip() or "00:00"
        if title_text:
            key_points.append(f"{time_text}：{title_text}")
        elif desc_text:
            key_points.append(f"{time_text}：{desc_text}")
        if len(key_points) >= limit:
            break
    while len(key_points) < 3:
        key_points.append("00:00：待确认要点")
    return key_points[:limit]


def _build_result_meta_from_steps(
    *,
    video_path: Path,
    steps: List[Dict[str, Any]],
    result_mode: str,
    fallback_used: bool,
    degrade_reason: str = "",
    analysis_note: str = "",
) -> Dict[str, Any]:
    normalized_mode = str(result_mode or "steps").strip() or "steps"
    title_seed = _compact_text(video_path.stem.replace("_", " ").replace("-", " "), 28) or "当前视频"
    if normalized_mode == "steps":
        content_title = f"{title_seed} 标准步骤结果"
        confidence_note = "已提炼出标准步骤结构，可直接用于复盘与文档生成。"
    elif normalized_mode == "candidate_steps":
        content_title = f"{title_seed} 候选步骤（低置信度）"
        confidence_note = "候选步骤由字幕自动抽取，建议结合原视频确认。"
    elif normalized_mode == "timeline_summary":
        content_title = f"{title_seed} 时间线摘要"
        confidence_note = "当前为摘要保底模式，步骤细粒度较低。"
    else:
        content_title = f"{title_seed} 分析结果"
        confidence_note = "系统已输出可读结果，建议按需复核。"

    timeline = _extract_timeline_from_steps(steps)
    key_points = _build_key_points_from_steps(steps)
    return {
        "result_mode": normalized_mode,
        "fallback_used": bool(fallback_used),
        "quality_score": _resolve_quality_score(
            normalized_mode,
            steps,
            fallback_used,
            degrade_reason=str(degrade_reason or "").strip(),
        ),
        "degrade_reason": str(degrade_reason or "").strip(),
        "analysis_note": str(analysis_note or "").strip(),
        "content_title": content_title,
        "key_points": key_points,
        "timeline_points": timeline,
        "confidence_note": confidence_note,
    }


def _build_blocked_notice_payload(risk: Dict[str, Any]) -> Dict[str, Any]:
    risk_level = str(risk.get("risk_level", "high")).strip().lower() or "high"
    reason_code = str(risk.get("reason_code", "CONTENT_POLICY_VIOLATION")).strip().upper()
    reason = str(risk.get("reason", "")).strip() or CONTENT_POLICY_BLOCK_MESSAGE
    return {
        "title": "安全检测未通过（已拦截）",
        "risk_level": risk_level,
        "reason_code": reason_code,
        "reason": reason,
        "suggestions": [
            "删除或替换涉及色情/裸露/血腥/暴力的敏感画面。",
            "对高风险片段进行裁剪、打码或弱化处理后再导出视频。",
            "完成整改后重新上传并发起安全检测。",
        ],
        "retry_guidance": "请先完成内容整改，再重新上传触发检测。",
    }


class VideoProcessingService:
    def process_video(
        self,
        video_path: Path,
        api_key: str,
        whisper_model: str,
        model_name: str,
        model_base_url: str,
        use_video: bool,
        web_search: bool,
        max_vision: int,
        fps: float = 1.0,
        summary_only: bool = False,
        history_owner_id: str = "",
        progress_callback: Callable[[str, str], None] | None = None,
    ) -> Tuple[List[Dict[str, Any]], str, str, str, bool, Dict[str, Any]]:
        def report(stage: str, message: str) -> None:
            if progress_callback:
                progress_callback(stage, message)

        report("prepare", "\u6b63\u5728\u51c6\u5907\u5206\u6790\u4efb\u52a1...")
        output_dir = _create_unique_output_dir(video_path)

        agent = VideoAnalyzerAgent(
            api_key if api_key else None,
            whisper_model,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        report("moderation", "正在执行黑名单指纹比对...")
        video_fingerprint = _compute_video_fingerprint_safely(video_path, "analyze")
        if video_fingerprint:
            blacklist_risk = _match_blacklisted_video_fingerprint_by_hash(
                video_fingerprint, source="analyze"
            )
        else:
            blacklist_risk = _match_blacklisted_video_fingerprint(video_path, source="analyze")
        if blacklist_risk is not None:
            quarantine_path = _quarantine_upload_file(video_path, str(blacklist_risk.get("reason_code", "")))
            if quarantine_path is not None:
                blacklist_risk["quarantine_path"] = str(quarantine_path)
            shutil.rmtree(output_dir, ignore_errors=True)
            raise ContentPolicyBlockedError(
                "视频命中黑名单指纹（SHA-256 完全一致），已拒绝处理。",
                blacklist_risk,
            )

        report("moderation", "正在执行内容风控检测...")
        risk_cache_model_key = _build_upload_risk_model_cache_key_from_agent(agent)
        risk_frame_dir = output_dir / ".risk_frames"
        cached_risk = (
            _get_cached_upload_risk_result(video_fingerprint, risk_cache_model_key)
            if video_fingerprint and risk_cache_model_key
            else None
        )
        if cached_risk is not None:
            logger.info("分析前风控缓存命中: sha256_prefix=%s", video_fingerprint[:12])
            cached_risk["cache_hit"] = True
            cached_risk["cache_source"] = "analyze_risk_precheck"
            if not str(cached_risk.get("hash_sha256", "")).strip():
                cached_risk["hash_sha256"] = video_fingerprint
            risk = cached_risk
        else:
            risk_agent = VideoAnalyzerAgent(
                api_key if api_key else None,
                "tiny",
                model_name=model_name,
                model_base_url=model_base_url,
            )
            risk, risk_frame_dir = _run_video_risk_gate(
                risk_agent,
                video_path,
                output_dir,
                subtitle_cache_identity=video_fingerprint,
            )
            if video_fingerprint and not str(risk.get("hash_sha256", "")).strip():
                risk["hash_sha256"] = video_fingerprint
            if (
                video_fingerprint
                and risk_cache_model_key
                and not _is_risk_infra_failure(risk)
                and not _should_block_by_risk(str(risk.get("decision", "")))
            ):
                _set_cached_upload_risk_result(video_fingerprint, risk_cache_model_key, risk)

        if _is_risk_infra_failure(risk):
            if risk_frame_dir.exists():
                shutil.rmtree(risk_frame_dir, ignore_errors=True)
            shutil.rmtree(output_dir, ignore_errors=True)
            raise RuntimeError(
                str(risk.get("provider_error") or risk.get("reason") or "风控服务不可用")
            )
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    video_fingerprint, risk, source="analyze_risk_block"
                )
                if video_fingerprint
                else _register_blocked_video_fingerprint(
                    video_path, risk, source="analyze_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            quarantine_path = _quarantine_upload_file(video_path, str(risk.get("reason_code", "")))
            if quarantine_path is not None:
                risk["quarantine_path"] = str(quarantine_path)
            shutil.rmtree(output_dir, ignore_errors=True)
            raise ContentPolicyBlockedError(
                f"视频触发风控策略（{risk.get('reason_code', 'CONTENT_POLICY_VIOLATION')}）：{risk.get('reason', '内容敏感')}",
                risk,
            )

        if risk_frame_dir.exists():
            shutil.rmtree(risk_frame_dir, ignore_errors=True)

        video_dest = output_dir / video_path.name
        if not video_dest.exists():
            shutil.copy2(video_path, video_dest)

        report("prepare", "正在评估长视频预处理策略...")
        analysis_video_path, analysis_preprocess_meta = _prepare_long_video_analysis_source(
            agent=agent,
            video_path=video_path,
            output_dir=output_dir,
        )
        analysis_subtitle_cache_identity: str | None = video_fingerprint or None
        if analysis_video_path != video_path and video_fingerprint:
            analysis_subtitle_cache_identity = f"{video_fingerprint}:analysis_proxy"
        if analysis_preprocess_meta.get("used"):
            report(
                "prepare",
                (
                    "长视频已完成切片/压缩预处理，正在使用优化副本继续分析"
                    if str(analysis_preprocess_meta.get("strategy", "")).strip() == "slice_then_compress"
                    else "长视频已完成压缩预处理，正在使用优化副本继续分析"
                ),
            )

        srt_path: str | None = None
        steps: List[Dict[str, Any]] = []
        analysis_error = ""
        fallback_used = bool(summary_only)
        result_mode = "steps"
        analysis_note = "已按要求仅生成摘要版内容。" if summary_only else ""
        degrade_reason = "user_requested_summary_only" if summary_only else ""
        result_meta: Dict[str, Any] = {}

        if not use_video:
            report("subtitle", "\u6b63\u5728\u751f\u6210\u5b57\u5e55...")
            try:
                srt_path = agent.generate_subtitles(
                    str(analysis_video_path),
                    str(output_dir),
                    cache_identity=analysis_subtitle_cache_identity,
                )
            except Exception as exc:
                analysis_error = f"字幕生成失败: {str(exc)}"
                logger.warning("Whisper 字幕生成失败，切换候选内容生成: %s", exc)
                srt_path = None

            if srt_path:
                _maybe_correct_subtitles(agent, srt_path, report)

            if srt_path and not summary_only:
                report("analysis", "\u6b63\u5728\u5206\u6790\u5b57\u5e55\u5185\u5bb9...")
                try:
                    steps = _run_async(agent.analyze_subtitles(srt_path))
                except Exception as exc:
                    analysis_error = f"字幕步骤识别失败: {str(exc)}"
                    logger.warning("字幕步骤识别失败，切换候选内容生成: %s", exc)
                    steps = []
        else:
            report("subtitle", "\u6b63\u5728\u5c1d\u8bd5\u751f\u6210\u5b57\u5e55...")
            try:
                srt_path = agent.generate_subtitles(
                    str(analysis_video_path),
                    str(output_dir),
                    cache_identity=analysis_subtitle_cache_identity,
                )
            except Exception as exc:
                logger.warning("Whisper 字幕生成失败，继续视频分析模式: %s", exc)
                srt_path = None

            if srt_path:
                _maybe_correct_subtitles(agent, srt_path, report)

            if not summary_only:
                report("analysis", "\u6b63\u5728\u5206\u6790\u89c6\u9891\u753b\u9762...")
                try:
                    steps = _run_async(agent.analyze_video(str(analysis_video_path), fps))
                except Exception as exc:
                    analysis_error = f"视频步骤识别失败: {str(exc)}"
                    logger.warning("视频步骤识别失败，切换候选内容生成: %s", exc)
                    steps = []

        if summary_only:
            report("analysis", "\u5df2\u542f\u7528\u4ec5\u751f\u6210\u6458\u8981\u6a21\u5f0f\uff0c\u6b63\u5728\u6784\u5efa\u65f6\u95f4\u7ebf\u6458\u8981...")
            summary_subtitles: List[Dict[str, Any]] = []
            if srt_path and Path(srt_path).exists():
                try:
                    summary_subtitles = agent.parse_srt(srt_path)
                except Exception as exc:
                    logger.warning("摘要模式解析字幕失败，改用无字幕摘要保底: %s", exc)
                    summary_subtitles = []
            summary_steps, timeline_points, summary_title, key_points = _build_timeline_summary_steps(
                video_path=video_path,
                subtitles=summary_subtitles,
                reason=analysis_error,
            )
            steps = summary_steps
            result_mode = "timeline_summary"
            fallback_used = True
            result_meta = {
                "result_mode": result_mode,
                "fallback_used": True,
                "degrade_reason": degrade_reason or "user_requested_summary_only",
                "analysis_note": analysis_note or "已根据你的选择仅生成摘要版内容。",
                "content_title": summary_title,
                "key_points": key_points[:5],
                "timeline_points": timeline_points[:5],
                "confidence_note": "摘要版输出不追求完整步骤，重点保证可读摘要与时间线。",
            }

        if not steps:
            report("analysis", "\u672a\u8bc6\u522b\u5230\u6807\u51c6\u6b65\u9aa4\uff0c\u6b63\u5728\u751f\u6210\u5019\u9009\u5185\u5bb9...")
            steps, fallback_meta, fallback_srt_path = _build_fallback_steps_when_empty(
                agent=agent,
                video_path=analysis_video_path,
                output_dir=output_dir,
                srt_path=srt_path,
                subtitle_cache_identity=analysis_subtitle_cache_identity or "",
                reason=analysis_error,
            )
            if fallback_srt_path and not srt_path:
                srt_path = fallback_srt_path
            fallback_used = bool(steps)
            result_mode = str(fallback_meta.get("result_mode", "timeline_summary"))
            analysis_note = str(fallback_meta.get("analysis_note", "")).strip() or analysis_note
            degrade_reason = str(fallback_meta.get("degrade_reason", "")).strip() or degrade_reason
            result_meta = dict(fallback_meta)
            if fallback_used:
                report("analysis", "\u5df2\u81ea\u52a8\u751f\u6210\u964d\u7ea7\u5185\u5bb9\uff0c\u5c06\u7ee7\u7eed\u751f\u6210\u6587\u6863")
            else:
                report("analysis", "\u5df2\u5b8c\u6210\u6446\u5e95\u5904\u7406\uff0c\u5c06\u8fd4\u56de\u6458\u8981\u7ed3\u679c")

        if not steps:
            report("analysis", "\u6807\u51c6\u4e0e\u5019\u9009\u6b65\u9aa4\u5747\u4e0d\u53ef\u7528\uff0c\u5df2\u542f\u52a8\u7d27\u6025\u6458\u8981\u4fdd\u5e95...")
            emergency_subtitles: List[Dict[str, Any]] = []
            if srt_path and Path(srt_path).exists():
                try:
                    emergency_subtitles = agent.parse_srt(srt_path)
                except Exception as exc:
                    logger.warning("紧急摘要解析字幕失败，改用无字幕摘要保底: %s", exc)
                    emergency_subtitles = []
            summary_steps, timeline_points, summary_title, key_points = _build_timeline_summary_steps(
                video_path=video_path,
                subtitles=emergency_subtitles,
                reason=analysis_error or "fallback_content_generation_failed",
            )
            steps = summary_steps
            result_mode = "timeline_summary"
            fallback_used = True
            analysis_note = (
                analysis_note
                or "未识别到标准步骤，已自动切换为紧急摘要保底结果。"
            )
            degrade_reason = (
                degrade_reason or "content_generation_failed_emergency_summary_generated"
            )
            result_meta = {
                "result_mode": result_mode,
                "fallback_used": True,
                "analysis_note": analysis_note,
                "degrade_reason": degrade_reason,
                "content_title": summary_title,
                "key_points": key_points[:5],
                "timeline_points": timeline_points[:5],
                "confidence_note": "当前为紧急摘要保底模式，建议结合原视频复核细节。",
            }

        image_dir = output_dir / "images"
        image_dir.mkdir(exist_ok=True)
        report("screenshots", "\u6b63\u5728\u751f\u6210\u5173\u952e\u622a\u56fe...")
        agent.generate_screenshots_from_steps(str(video_path), steps, str(image_dir))

        if max_vision > 0 and not use_video and srt_path and not fallback_used:
            report("vision", "\u6b63\u5728\u8fdb\u884c\u89c6\u89c9\u589e\u5f3a...")
            steps = _run_async(
                agent.enhance_steps_with_vision(
                    steps, str(image_dir), srt_path=srt_path, max_calls=max_vision
                )
            )

        output_md = output_dir / "operation_guide.md"
        report("document", "\u6b63\u5728\u751f\u6210\u603b\u7ed3\u6587\u6863...")
        _run_async(
            agent.generate_step_document(
                steps=steps,
                output_path=str(output_md),
                srt_path=srt_path if srt_path else None,
                image_dir="images",
                web_search=web_search,
            )
        )

        output_pdf = output_dir / "operation_guide.pdf"
        report("pdf", "\u6b63\u5728\u751f\u6210 PDF...")
        agent.generate_pdf(str(output_md), str(output_pdf))
        agent.save_results(steps, str(output_dir / "steps.json"))
        output_media = _build_output_media_bundle(
            output_dir,
            preferred_video_name=video_path.name,
            preferred_srt_path=srt_path or "",
        )
        report("done", "\u5f53\u524d\u89c6\u9891\u5206\u6790\u5b8c\u6210")

        has_steps = len(steps) > 0
        normalized_meta = _build_result_meta_from_steps(
            video_path=video_path,
            steps=steps,
            result_mode=result_mode,
            fallback_used=fallback_used,
            degrade_reason=degrade_reason,
            analysis_note=analysis_note,
        )
        if isinstance(result_meta, dict):
            normalized_meta.update({k: v for k, v in result_meta.items() if v not in (None, "")})
        result_meta = normalized_meta
        if output_media:
            result_meta["output_media"] = output_media
        if isinstance(analysis_preprocess_meta, dict):
            result_meta["analysis_preprocess"] = {
                k: v for k, v in analysis_preprocess_meta.items() if v not in ("", None)
            }
        if analysis_error:
            result_meta["analysis_error"] = _compact_text(analysis_error, 180)
        if has_steps:
            record = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "video_name": video_path.name,
                "output_dir": str(output_dir),
                "steps_count": len(steps),
                "mode": "video" if use_video else "subtitle",
                "whisper_model": whisper_model,
                "model_name": model_name,
                "model_base_url": model_base_url,
                "use_video": use_video,
                "web_search": web_search,
                "max_vision": max_vision,
                "pdf_path": str(output_pdf),
                "risk_decision": str(risk.get("decision", "allow")),
                "risk_level": str(risk.get("risk_level", "low")),
                "risk_reason_code": str(risk.get("reason_code", "SAFE_CONTENT")),
                "result_mode": result_meta.get("result_mode", result_mode),
                "fallback_used": bool(result_meta.get("fallback_used", fallback_used)),
                "analysis_note": str(result_meta.get("analysis_note", analysis_note)),
                "quality_score": _safe_float(result_meta.get("quality_score", 0.0), 0.0, 0.0, 1.0),
                "degrade_reason": str(result_meta.get("degrade_reason", "")).strip(),
                "content_title": str(result_meta.get("content_title", "")).strip(),
                "confidence_note": str(result_meta.get("confidence_note", "")).strip(),
                "analysis_preprocess_used": bool(analysis_preprocess_meta.get("used", False)),
                "analysis_preprocess_strategy": str(
                    analysis_preprocess_meta.get("strategy", "")
                ).strip(),
                "analysis_video_path": (
                    str(analysis_video_path) if analysis_video_path != video_path else ""
                ),
            }
            save_history(record, history_owner_id)

        with open(output_md, "r", encoding="utf-8") as f:
            md_content = f.read()

        return steps, md_content, str(output_dir), str(output_pdf), has_steps, result_meta


video_processing_service = VideoProcessingService()


class BackendServiceContainer:
    def __init__(self):
        self.risk_fallback_env = risk_fallback_env_service
        self.progress = progress_state_service
        self.risk_blocklist = risk_blocklist_service
        self.risk_result_cache = risk_result_cache_service
        self.history = history_service
        self.history_retention = history_retention_cleanup_service
        self.upload_session = upload_session_service
        self.upload_risk = upload_risk_service
        self.upload_video_cleanup = upload_video_auto_cleanup_service
        self.video_processing = video_processing_service


backend_services = BackendServiceContainer()


def process_video(
    video_path: Path,
    api_key: str,
    whisper_model: str,
    model_name: str,
    model_base_url: str,
    use_video: bool,
    web_search: bool,
    max_vision: int,
    fps: float = 1.0,
    summary_only: bool = False,
    history_owner_id: str = "",
    progress_callback: Callable[[str, str], None] | None = None,
) -> Tuple[List[Dict[str, Any]], str, str, str, bool, Dict[str, Any]]:
    return video_processing_service.process_video(
        video_path=video_path,
        api_key=api_key,
        whisper_model=whisper_model,
        model_name=model_name,
        model_base_url=model_base_url,
        use_video=use_video,
        web_search=web_search,
        max_vision=max_vision,
        fps=fps,
        summary_only=summary_only,
        history_owner_id=history_owner_id,
        progress_callback=progress_callback,
    )


@app.route("/")
def index():
    return jsonify(
        {
            "service": "video-to-doc-api",
            "status": "ok",
            "frontend": "Run web-react independently (e.g. npm run dev in /web-react).",
        }
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "不支持的文件格式"}), 400

    staged_path = _build_upload_staging_path(file.filename)
    try:
        file.save(str(staged_path))
        if not is_valid_video_content(staged_path):
            _safe_remove_file(staged_path)
            return jsonify({"error": "文件内容不是有效的视频格式"}), 400
        segment_policy = _build_video_segment_policy(staged_path)
        if bool(segment_policy.get("requires_trim")):
            _safe_remove_file(staged_path)
            return (
                jsonify(
                    _build_segment_policy_reject_payload(
                        segment_policy,
                        code="video_segment_trim_required",
                        error_message=(
                            "当前视频属于裁剪优先区（超长或超大文件），"
                            "请先裁剪后再上传。"
                        ),
                    )
                ),
                400,
            )

        blacklist_risk, file_fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staged_path,
            source="upload_single",
        )
        if blacklist_risk is not None:
            _safe_remove_file(staged_path)
            return jsonify(_risk_reject_payload(blacklist_risk)), 403

        risk, file_fingerprint, _ = _run_upload_pre_risk_check(
            staged_video_path=staged_path,
            risk_agent=None,
            source="upload_single",
            file_fingerprint=file_fingerprint,
            skip_blacklist=True,
        )
        if _is_risk_infra_failure(risk):
            _safe_remove_file(staged_path)
            logger.warning("上传风控服务异常（single upload）: %s", risk)
            payload, status_code = _build_upload_risk_failure_response(risk)
            return jsonify(payload), status_code
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    file_fingerprint, risk, source="upload_single_risk_block"
                )
                if file_fingerprint
                else _register_blocked_video_fingerprint(
                    staged_path, risk, source="upload_single_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            _safe_remove_file(staged_path)
            return jsonify(_risk_reject_payload(risk)), 403

        save_path = _build_unique_upload_path(file.filename)
        shutil.move(str(staged_path), str(save_path))
        _mark_uploaded_video_loaded_now(save_path)
        return jsonify(
            {
                "filename": save_path.name,
                "filepath": str(save_path),
                "segment_policy": segment_policy,
            }
        )
    except ValueError as exc:
        _safe_remove_file(staged_path)
        logger.warning("上传风控不可用（single upload）: %s", exc)
        return jsonify(_upload_risk_unavailable_payload()), 503
    except Exception as exc:
        _safe_remove_file(staged_path)
        return jsonify({"error": f"上传失败: {str(exc)}"}), 500


@app.route("/upload_url", methods=["POST"])
def upload_from_url():
    data = _json_payload()
    try:
        source_url = _normalize_source_url(data.get("url", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    requested_name = _safe_video_filename(
        str(data.get("filename", "")).strip()
        or _guess_video_filename_from_url(source_url, fallback="url_video.mp4"),
        fallback_stem="url_video",
    )
    staged_path = _build_upload_staging_path(requested_name)

    download_meta: Dict[str, Any] = {}
    try:
        downloaded_path, download_meta = _download_video_from_url(source_url, staged_path)
        staged_path = downloaded_path
        resolved_filename = _safe_video_filename(staged_path.name, fallback_stem="url_video")

        if not is_valid_video_content(staged_path):
            _safe_remove_file(staged_path)
            return jsonify({"error": "下载内容不是有效的视频格式"}), 400

        segment_policy = _build_video_segment_policy(staged_path)
        if bool(segment_policy.get("requires_trim")):
            _safe_remove_file(staged_path)
            return (
                jsonify(
                    _build_segment_policy_reject_payload(
                        segment_policy,
                        code="video_segment_trim_required",
                        error_message=(
                            "当前视频属于裁剪优先区（超长或超大文件），"
                            "请先裁剪后再上传。"
                        ),
                    )
                ),
                400,
            )

        blacklist_risk, file_fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staged_path,
            source="upload_url",
        )
        if blacklist_risk is not None:
            _safe_remove_file(staged_path)
            return jsonify(_risk_reject_payload(blacklist_risk)), 403

        risk, file_fingerprint, _ = _run_upload_pre_risk_check(
            staged_video_path=staged_path,
            risk_agent=None,
            source="upload_url",
            file_fingerprint=file_fingerprint,
            skip_blacklist=True,
        )
        if _is_risk_infra_failure(risk):
            _safe_remove_file(staged_path)
            logger.warning("上传风控服务异常（url upload）: %s", risk)
            payload, status_code = _build_upload_risk_failure_response(risk)
            return jsonify(payload), status_code
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    file_fingerprint, risk, source="upload_url_risk_block"
                )
                if file_fingerprint
                else _register_blocked_video_fingerprint(
                    staged_path, risk, source="upload_url_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            _safe_remove_file(staged_path)
            return jsonify(_risk_reject_payload(risk)), 403

        save_path = _build_unique_upload_path(resolved_filename)
        shutil.move(str(staged_path), str(save_path))
        _mark_uploaded_video_loaded_now(save_path)
        return jsonify(
            {
                "success": True,
                "filename": save_path.name,
                "filepath": str(save_path),
                "segment_policy": segment_policy,
                "source_url": source_url,
                "resolved_source_url": str(download_meta.get("resolved_source_url", "")).strip(),
                "download_source": str(download_meta.get("download_source", "")).strip(),
                "yt_dlp_cookie_source": str(
                    download_meta.get("yt_dlp_cookie_source", "")
                ).strip(),
                "download_title": str(download_meta.get("title", "")).strip(),
                "scraped_page_title": str(download_meta.get("scraped_page_title", "")).strip(),
                "scraped_final_url": str(download_meta.get("scraped_final_url", "")).strip(),
                "scraped_canonical_url": str(
                    download_meta.get("scraped_canonical_url", "")
                ).strip(),
                "expected_media_ids": download_meta.get("expected_media_ids", []),
                "resolved_video_id": str(download_meta.get("video_id", "")).strip(),
                "candidate_batch": str(download_meta.get("candidate_batch", "")).strip(),
                "scrape_fetch_method": str(download_meta.get("scrape_fetch_method", "")).strip(),
                "scrape_challenge_detected": bool(
                    download_meta.get("scrape_challenge_detected", False)
                ),
                "scrape_challenge_signals": download_meta.get("scrape_challenge_signals", []),
            }
        )
    except ValueError as exc:
        _safe_remove_file(staged_path)
        logger.warning("上传风控不可用（url upload）: %s", exc)
        return jsonify(_upload_risk_unavailable_payload()), 503
    except Exception as exc:
        _safe_remove_file(staged_path)
        return jsonify({"error": f"链接上传失败: {str(exc)}"}), 500


@app.route("/upload_chunk_init", methods=["POST"])
def upload_chunk_init():
    data = _json_payload()
    filename = str(data.get("filename", "")).strip()
    if not filename:
        return jsonify({"error": "文件名不能为空"}), 400
    if not allowed_file(filename):
        return jsonify({"error": "不支持的文件格式"}), 400

    total_size = _safe_int(data.get("total_size"), 0, 1)
    if total_size <= 0:
        return jsonify({"error": "文件大小无效"}), 400
    total_size_mb = float(total_size) / (1024.0 * 1024.0)
    if total_size_mb >= VIDEO_SEGMENT_CROP_REQUIRED_MIN_SIZE_MB:
        return (
            jsonify(
                {
                    "error": (
                        f"文件大小约 {total_size_mb:.1f}MB，已进入裁剪优先区；"
                        "请先裁剪后再上传。"
                    ),
                    "code": "video_segment_trim_required",
                    "segment_policy": {
                        "zone": "trim_required",
                        "zone_label": "裁剪优先区",
                        "duration_seconds": None,
                        "duration_text": "未知",
                        "file_size_mb": round(total_size_mb, 2),
                        "requires_trim": True,
                        "allow_upload": False,
                        "allow_batch": False,
                    },
                }
            ),
            400,
        )

    requested_chunk_size = _safe_int(
        data.get("chunk_size", DEFAULT_UPLOAD_CHUNK_SIZE),
        DEFAULT_UPLOAD_CHUNK_SIZE,
        256 * 1024,
        MAX_UPLOAD_CHUNK_SIZE,
    )
    file_key = str(data.get("file_key", "")).strip()
    _, upload_model_name, upload_model_base_url = _normalize_upload_model_options(data)
    upload_api_key = ""

    try:
        requested_upload_id = _normalize_upload_id(data.get("upload_id", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with upload_session_lock:
        session: Dict[str, Any] | None = None
        upload_id = requested_upload_id

        if upload_id:
            session = _load_upload_session(upload_id)
            if session is not None:
                same_name = str(session.get("filename", "")) == filename
                same_size = _safe_int(session.get("total_size"), -1) == total_size
                same_key = not file_key or str(session.get("file_key", "")) == file_key
                same_model = (
                    str(session.get("risk_api_key", "")).strip() == upload_api_key
                    and str(session.get("risk_model_name", "")).strip()
                    == upload_model_name
                    and str(session.get("risk_model_base_url", "")).strip()
                    == upload_model_base_url
                )
                if not (same_name and same_size and same_key and same_model):
                    session = None
                else:
                    total_chunks = _safe_int(session.get("total_chunks"), 1, 1)
                    received_chunks = _normalize_received_chunks(
                        session.get("received_chunks", []), total_chunks
                    )
                    session["received_chunks"] = received_chunks
                    if _get_chunk_storage_mode(session) == "memory":
                        if upload_id not in upload_memory_buffers and received_chunks:
                            # Memory-mode sessions cannot recover buffered chunks after process restart.
                            _delete_upload_session(upload_id)
                            session = None
                        elif upload_id not in upload_memory_buffers:
                            if _reserve_upload_memory(upload_id, total_size):
                                session["storage_mode"] = "memory"
                            else:
                                session["storage_mode"] = "disk"

        if session is None:
            upload_id = uuid4().hex
            total_chunks = max(1, (total_size + requested_chunk_size - 1) // requested_chunk_size)
            storage_mode = "disk"
            if total_size <= UPLOAD_IN_MEMORY_MAX_FILE_SIZE and _reserve_upload_memory(
                upload_id, total_size
            ):
                storage_mode = "memory"
            session = {
                "upload_id": upload_id,
                "filename": filename,
                "file_key": file_key,
                "total_size": total_size,
                "chunk_size": requested_chunk_size,
                "total_chunks": total_chunks,
                "received_chunks": [],
                "storage_mode": storage_mode,
                "risk_api_key": upload_api_key,
                "risk_model_name": upload_model_name,
                "risk_model_base_url": upload_model_base_url,
                "created_at": now_text,
                "updated_at": now_text,
            }
            try:
                _save_upload_session(upload_id, session)
            except Exception:
                if storage_mode == "memory":
                    _release_upload_memory(upload_id)
                raise
        else:
            total_chunks = _safe_int(session.get("total_chunks"), 1, 1)
            session["received_chunks"] = _normalize_received_chunks(
                session.get("received_chunks", []), total_chunks
            )
            if _get_chunk_storage_mode(session) == "memory":
                if not _reserve_upload_memory(upload_id, total_size):
                    session["storage_mode"] = "disk"
            else:
                _release_upload_memory(upload_id)
            session["risk_api_key"] = upload_api_key
            session["risk_model_name"] = upload_model_name
            session["risk_model_base_url"] = upload_model_base_url
            session["updated_at"] = now_text
            _save_upload_session(upload_id, session)

    return jsonify(
        {
            "success": True,
            "upload_id": upload_id,
            "chunk_size": _safe_int(session.get("chunk_size"), DEFAULT_UPLOAD_CHUNK_SIZE, 1),
            "total_chunks": _safe_int(session.get("total_chunks"), 1, 1),
            "received_chunks": session.get("received_chunks", []),
            "storage_mode": _get_chunk_storage_mode(session),
        }
    )


@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    if "chunk" not in request.files:
        return jsonify({"error": "缺少分片文件"}), 400

    try:
        upload_id = _normalize_upload_id(request.form.get("upload_id", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not upload_id:
        return jsonify({"error": "upload_id 不能为空"}), 400

    chunk_index = _safe_int(request.form.get("chunk_index"), -1)
    if chunk_index < 0:
        return jsonify({"error": "chunk_index 无效"}), 400

    chunk_file = request.files["chunk"]
    chunk_data = chunk_file.read() or b""

    with upload_session_lock:
        session = _load_upload_session(upload_id)
        if session is None:
            return jsonify({"error": "上传会话不存在，请重新开始上传"}), 404

        total_chunks = _safe_int(session.get("total_chunks"), 0, 1)
        chunk_size = _safe_int(
            session.get("chunk_size"), DEFAULT_UPLOAD_CHUNK_SIZE, 1, MAX_UPLOAD_CHUNK_SIZE
        )
        total_size = _safe_int(session.get("total_size"), 0, 1)

        if chunk_index >= total_chunks:
            return jsonify({"error": "chunk_index 超出范围"}), 400

        offset = chunk_index * chunk_size
        if offset >= total_size:
            return jsonify({"error": "分片偏移量无效"}), 400

        expected_max_size = min(chunk_size, total_size - offset)
        if len(chunk_data) == 0 and expected_max_size > 0:
            return jsonify({"error": "分片内容为空"}), 400
        if len(chunk_data) > expected_max_size:
            return jsonify({"error": "分片大小超出限制"}), 400

        storage_mode = _get_chunk_storage_mode(session)
        if storage_mode == "memory":
            chunk_buffer = upload_memory_buffers.get(upload_id)
            existing_received = _normalize_received_chunks(
                session.get("received_chunks", []), total_chunks
            )
            if chunk_buffer is None and existing_received:
                _delete_upload_session(upload_id)
                return jsonify({"error": "上传会话已过期，请重新开始上传"}), 409
            if chunk_buffer is None:
                if not _reserve_upload_memory(upload_id, total_size):
                    return jsonify({"error": "上传繁忙，请稍后重试"}), 503
                session["storage_mode"] = "memory"
                chunk_buffer = upload_memory_buffers.setdefault(upload_id, {})
            chunk_buffer[chunk_index] = chunk_data
        else:
            temp_path = _upload_session_temp_path(upload_id)
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            if not temp_path.exists():
                with open(temp_path, "wb"):
                    pass

            with open(temp_path, "r+b") as f:
                f.seek(offset)
                f.write(chunk_data)

        received_chunks = set(
            _normalize_received_chunks(session.get("received_chunks", []), total_chunks)
        )
        received_chunks.add(chunk_index)
        session["received_chunks"] = sorted(received_chunks)
        session["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_upload_session(upload_id, session)

    return jsonify(
        {
            "success": True,
            "upload_id": upload_id,
            "uploaded_chunks": len(session["received_chunks"]),
            "total_chunks": total_chunks,
        }
    )


@app.route("/upload_chunk_finalize", methods=["POST"])
def upload_chunk_finalize():
    data = _json_payload()
    try:
        upload_id = _normalize_upload_id(data.get("upload_id", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not upload_id:
        return jsonify({"error": "upload_id 不能为空"}), 400

    filename = ""
    total_size = 0
    staging_path: Path | None = None

    with upload_session_lock:
        session = _load_upload_session(upload_id)
        if session is None:
            return jsonify({"error": "上传会话不存在，请重新开始上传"}), 404

        filename = str(session.get("filename", "")).strip()
        if not filename or not allowed_file(filename):
            return jsonify({"error": "原始文件名无效"}), 400

        total_chunks = _safe_int(session.get("total_chunks"), 0, 1)
        total_size = _safe_int(session.get("total_size"), 0, 1)
        received_chunks = _normalize_received_chunks(session.get("received_chunks", []), total_chunks)
        if len(received_chunks) < total_chunks:
            received_set = set(received_chunks)
            missing_chunks = [i for i in range(total_chunks) if i not in received_set][:10]
            missing_text = ",".join(str(i) for i in missing_chunks)
            suffix = "..." if len(received_chunks) + len(missing_chunks) < total_chunks else ""
            return jsonify({"error": f"分片未上传完整，缺少分片: {missing_text}{suffix}"}), 400

        storage_mode = _get_chunk_storage_mode(session)
        staging_path = _build_upload_staging_path(filename)
        if storage_mode == "memory":
            chunk_buffer = upload_memory_buffers.get(upload_id)
            if chunk_buffer is None:
                _delete_upload_session(upload_id)
                return jsonify({"error": "上传会话已过期，请重新开始上传"}), 409

            all_missing = [i for i in range(total_chunks) if i not in chunk_buffer]
            missing_buffer = all_missing[:10]
            if missing_buffer:
                missing_text = ",".join(str(i) for i in missing_buffer)
                suffix = "..." if len(all_missing) > len(missing_buffer) else ""
                return jsonify({"error": f"分片缓存不完整，缺少分片: {missing_text}{suffix}"}), 400

            with open(staging_path, "wb") as f:
                for idx in range(total_chunks):
                    f.write(chunk_buffer.get(idx, b""))
                if f.tell() > total_size:
                    f.truncate(total_size)
        else:
            temp_path = _upload_session_temp_path(upload_id)
            if not temp_path.exists():
                return jsonify({"error": "临时文件不存在，请重新上传"}), 400

            if temp_path.stat().st_size < total_size:
                return jsonify({"error": "文件尚未完整上传，请继续上传缺失分片"}), 400

            if temp_path.stat().st_size > total_size:
                with open(temp_path, "r+b") as f:
                    f.truncate(total_size)

            shutil.move(str(temp_path), str(staging_path))
        _delete_upload_session(upload_id)

    if staging_path is None:
        return jsonify({"error": "上传文件状态异常"}), 500

    try:
        if not is_valid_video_content(staging_path):
            _safe_remove_file(staging_path)
            return jsonify({"error": "文件内容不是有效的视频格式"}), 400
        segment_policy = _build_video_segment_policy(staging_path)
        if bool(segment_policy.get("requires_trim")):
            _safe_remove_file(staging_path)
            return (
                jsonify(
                    _build_segment_policy_reject_payload(
                        segment_policy,
                        code="video_segment_trim_required",
                        error_message=(
                            "当前视频属于裁剪优先区（超长或超大文件），"
                            "请先裁剪后再上传。"
                        ),
                    )
                ),
                400,
            )

        blacklist_risk, file_fingerprint = _check_upload_blacklist_precheck(
            staged_video_path=staging_path,
            source="upload_chunk_finalize",
        )
        if blacklist_risk is not None:
            _safe_remove_file(staging_path)
            return jsonify(_risk_reject_payload(blacklist_risk)), 403

        risk, file_fingerprint, _ = _run_upload_pre_risk_check(
            staged_video_path=staging_path,
            risk_agent=None,
            source="upload_chunk_finalize",
            file_fingerprint=file_fingerprint,
            skip_blacklist=True,
        )
        if _is_risk_infra_failure(risk):
            _safe_remove_file(staging_path)
            logger.warning("上传风控服务异常（chunk finalize）: %s", risk)
            payload, status_code = _build_upload_risk_failure_response(risk)
            return jsonify(payload), status_code
        if _should_block_by_risk(str(risk.get("decision", ""))):
            blocked_hash = (
                _register_blocked_video_fingerprint_by_hash(
                    file_fingerprint, risk, source="upload_chunk_finalize_risk_block"
                )
                if file_fingerprint
                else _register_blocked_video_fingerprint(
                    staging_path, risk, source="upload_chunk_finalize_risk_block"
                )
            )
            if blocked_hash:
                risk["hash_sha256"] = blocked_hash
            _safe_remove_file(staging_path)
            return jsonify(_risk_reject_payload(risk)), 403

        save_path = _build_unique_upload_path(filename)
        shutil.move(str(staging_path), str(save_path))
        _mark_uploaded_video_loaded_now(save_path)
        if save_path.stat().st_size > total_size:
            with open(save_path, "r+b") as f:
                f.truncate(total_size)
        return jsonify(
            {
                "success": True,
                "filename": save_path.name,
                "filepath": str(save_path),
                "segment_policy": segment_policy,
            }
        )
    except ValueError as exc:
        _safe_remove_file(staging_path)
        logger.warning("上传风控不可用（chunk finalize）: %s", exc)
        return jsonify(_upload_risk_unavailable_payload()), 503
    except Exception as exc:
        _safe_remove_file(staging_path)
        return jsonify({"error": f"上传失败: {str(exc)}"}), 500


@app.route("/analyze", methods=["POST"])
def analyze():
    data = _json_payload()
    history_owner_id = _ensure_history_owner()
    task_id = _resolve_progress_task_id(data.get("task_id", data.get("progress_task_id", "")))
    try:
        api_key, model_name, model_base_url = _read_shared_backend_model_options(
            require_api_key=True
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "task_id": task_id}), 503

    whisper_model, use_video, web_search, max_vision, fps = _normalize_processing_options(
        data
    )
    summary_only = _as_bool(data.get("summary_only", False))

    try:
        video_path = _resolve_upload_filepath(data.get("filepath"))
    except ValueError as exc:
        return jsonify({"error": str(exc), "task_id": task_id}), 400
    except FileNotFoundError:
        return jsonify({"error": "文件不存在", "task_id": task_id}), 400

    segment_policy = _build_video_segment_policy(video_path)
    if bool(segment_policy.get("requires_trim")):
        reject_payload = _build_segment_policy_reject_payload(
            segment_policy,
            code="video_segment_trim_required",
            error_message=(
                "当前视频属于裁剪优先区（超长或超大文件），"
                "请先裁剪后再分析。"
            ),
        )
        reject_payload["task_id"] = task_id
        return (
            jsonify(reject_payload),
            400,
        )

    (
        effective_use_video,
        effective_web_search,
        effective_max_vision,
        effective_summary_only,
        segment_guardrails,
    ) = _apply_video_segment_processing_guardrails(
        segment_policy,
        use_video=use_video,
        web_search=web_search,
        max_vision=max_vision,
        summary_only=summary_only,
    )

    try:
        _update_single_progress(
            owner_id=history_owner_id,
            task_id=task_id,
            status="processing",
            current_file=video_path.name,
            stage="prepare",
            message="\u4efb\u52a1\u5df2\u542f\u52a8\uff0c\u6b63\u5728\u521d\u59cb\u5316...",
        )

        def _single_progress_callback(stage: str, message: str) -> None:
            _update_single_progress(
                owner_id=history_owner_id,
                task_id=task_id,
                status="processing",
                current_file=video_path.name,
                stage=stage,
                message=message,
            )

        steps, md_content, output_dir, output_pdf, has_steps, result_meta = process_video(
            video_path,
            api_key,
            whisper_model,
            model_name,
            model_base_url,
            effective_use_video,
            effective_web_search,
            effective_max_vision,
            fps,
            summary_only=effective_summary_only,
            history_owner_id=history_owner_id,
            progress_callback=_single_progress_callback,
        )
        result_meta["segment_policy"] = segment_policy
        if segment_guardrails:
            result_meta["segment_guardrails"] = segment_guardrails
        _update_single_progress(
            owner_id=history_owner_id,
            task_id=task_id,
            status="completed",
            stage="done",
            message=(
                "\u89c6\u9891\u5206\u6790\u5df2\u5b8c\u6210\uff08\u5df2\u81ea\u52a8\u751f\u6210\u5019\u9009\u5185\u5bb9\uff09"
                if result_meta.get("fallback_used")
                else "\u89c6\u9891\u5206\u6790\u5df2\u5b8c\u6210"
            ),
        )
        output_media = (
            result_meta.get("output_media", {})
            if isinstance(result_meta.get("output_media", {}), dict)
            else {}
        )
        return jsonify(
            {
                "success": True,
                "steps": steps,
                "markdown": md_content,
                "output_dir": output_dir,
                "output_dir_name": str(output_media.get("output_dir_name", "")).strip()
                or Path(output_dir).name,
                "pdf_path": output_pdf,
                "has_steps": has_steps,
                "result_mode": result_meta.get("result_mode", "steps"),
                "fallback_used": bool(result_meta.get("fallback_used", False)),
                "analysis_note": str(result_meta.get("analysis_note", "")).strip(),
                "quality_score": _safe_float(result_meta.get("quality_score", 0.0), 0.0, 0.0, 1.0),
                "degrade_reason": str(result_meta.get("degrade_reason", "")).strip(),
                "content_title": str(result_meta.get("content_title", "")).strip(),
                "key_points": result_meta.get("key_points", []),
                "timeline_points": result_meta.get("timeline_points", []),
                "confidence_note": str(result_meta.get("confidence_note", "")).strip(),
                "task_id": task_id,
                "segment_policy": segment_policy,
                "segment_guardrails": segment_guardrails,
                "video_preview_url": str(output_media.get("video_preview_url", "")).strip(),
                "subtitle_available": bool(output_media.get("subtitle_available", False)),
                "subtitle_file_name": str(output_media.get("subtitle_file_name", "")).strip(),
                "subtitle_line_count": _safe_int(
                    output_media.get("subtitle_line_count"), 0, 0
                ),
                "subtitle_exports": output_media.get("subtitle_exports", {}),
                "subtitle_workbench_url": str(
                    output_media.get("subtitle_workbench_url", "")
                ).strip(),
                "effective_options": {
                    "use_video": effective_use_video,
                    "web_search": effective_web_search,
                    "max_vision": effective_max_vision,
                    "summary_only": effective_summary_only,
                },
            }
        )
    except ContentPolicyBlockedError as exc:
        _update_single_progress(
            owner_id=history_owner_id,
            task_id=task_id,
            status="failed",
            stage="moderation",
            message=str(exc),
        )
        blocked_notice = _build_blocked_notice_payload(exc.risk)
        return (
            jsonify(
                {
                    "error": str(exc),
                    "code": "content_policy_violation",
                    "risk": exc.risk,
                    "result_mode": "blocked_notice",
                    "quality_score": 0.0,
                    "degrade_reason": "content_policy_blocked",
                    "blocked_notice": blocked_notice,
                    "task_id": task_id,
                }
            ),
            403,
        )
    except Exception as exc:
        error_message, status_code, normalized = _normalize_provider_error(
            exc, default_status=500
        )
        _update_single_progress(
            owner_id=history_owner_id,
            task_id=task_id,
            status="failed",
            stage="failed",
            message=error_message,
        )
        payload: Dict[str, Any] = {"error": error_message, "task_id": task_id}
        if status_code >= 500 and not normalized:
            payload["trace"] = traceback.format_exc()
        return jsonify(payload), status_code


@app.route("/test_model", methods=["POST"])
def test_model():
    data = _json_payload()
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        return jsonify({"error": "请输入 API Key"}), 400

    model_name = str(data.get("model_name", "")).strip()
    model_base_url = str(data.get("model_base_url", "")).strip()
    if len(model_name) > 200:
        model_name = model_name[:200]
    if len(model_base_url) > 300:
        model_base_url = model_base_url[:300]

    if not model_name:
        return jsonify({"error": "请填写模型名称"}), 400
    if not model_base_url:
        return jsonify({"error": "请填写模型接口 Base URL"}), 400

    try:
        agent = VideoAnalyzerAgent(
            api_key=api_key,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        result = _run_async(agent.test_model_connection())
        return jsonify(
            {
                "success": True,
                "message": "模型连接测试成功",
                "model_name": model_name,
                "model_base_url": model_base_url,
                "reply": str(result.get("reply", "") or ""),
                "provider": str(result.get("provider", "") or ""),
            }
        )
    except Exception as exc:
        error_message, status_code, _ = _normalize_provider_error(exc, default_status=500)
        return jsonify({"error": f"模型连接测试失败：{error_message}"}), status_code


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename, as_attachment=True)


@app.route("/download_zip/<output_dir>")
def download_zip(output_dir):
    try:
        output_path = _resolve_output_dir(output_dir, must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "文件不存在"}), 404

    md_file = output_path / "operation_guide.md"
    if not md_file.exists():
        return jsonify({"error": "文件不存在"}), 404

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        _append_output_bundle_to_zip(zf, output_path, prefix="")

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{output_path.name}.zip",
    )


@app.route("/output/<path:filename>")
def serve_output_file(filename):
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename)


@app.route("/subtitle_workbench", methods=["GET"])
def subtitle_workbench():
    raw_output_dir = str(request.args.get("output_dir", "")).strip()
    if not raw_output_dir:
        return jsonify({"error": "缺少输出目录"}), 400

    try:
        output_path = _resolve_output_dir(raw_output_dir, must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "输出目录不存在"}), 404

    subtitle_file = _find_output_subtitle_file(output_path)
    if subtitle_file is None:
        return jsonify({"error": "未找到字幕文件"}), 404

    entries = _parse_srt_file_entries(subtitle_file)
    limit = _safe_int(request.args.get("limit"), 12000, 1, 50000)
    output_media = _build_output_media_bundle(
        output_path,
        preferred_srt_path=str(subtitle_file),
    )
    return jsonify(
        {
            "success": True,
            "output_dir": str(output_path),
            "output_dir_name": output_path.name,
            "subtitle_file": subtitle_file.name,
            "line_count": len(entries),
            "truncated": len(entries) > limit,
            "lines": entries[:limit],
            "video_preview_url": str(output_media.get("video_preview_url", "")).strip(),
            "subtitle_available": bool(output_media.get("subtitle_available", False)),
            "subtitle_exports": output_media.get("subtitle_exports", {}),
        }
    )


@app.route("/download_subtitle/<output_dir>")
def download_subtitle(output_dir):
    subtitle_format = str(request.args.get("format", "srt")).strip().lower()
    if subtitle_format not in {"srt", "vtt", "txt"}:
        return jsonify({"error": "不支持的字幕格式"}), 400

    try:
        output_path = _resolve_output_dir(output_dir, must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "输出目录不存在"}), 404

    subtitle_file = _find_output_subtitle_file(output_path)
    if subtitle_file is None:
        return jsonify({"error": "未找到字幕文件"}), 404

    subtitle_exports = _ensure_subtitle_exports(output_path, subtitle_file)
    export_path = subtitle_exports.get(subtitle_format)
    if export_path is None or not export_path.exists():
        return jsonify({"error": "字幕导出失败"}), 500

    mimetype_map = {
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "txt": "text/plain; charset=utf-8",
    }
    download_name = f"{output_path.name}_subtitle.{subtitle_format}"
    return send_file(
        export_path,
        mimetype=mimetype_map.get(subtitle_format, "application/octet-stream"),
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/download_subtitles_zip/<output_dir>")
def download_subtitles_zip(output_dir):
    try:
        output_path = _resolve_output_dir(output_dir, must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "输出目录不存在"}), 404

    subtitle_file = _find_output_subtitle_file(output_path)
    if subtitle_file is None:
        return jsonify({"error": "未找到字幕文件"}), 404

    subtitle_exports = _ensure_subtitle_exports(output_path, subtitle_file)
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for fmt in ("srt", "vtt", "txt"):
            export_path = subtitle_exports.get(fmt)
            if export_path is not None and export_path.exists():
                zf.write(export_path, f"subtitle.{fmt}")

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{output_path.name}_subtitles.zip",
    )


@app.route("/refresh_subtitle/<output_dir>", methods=["POST"])
def refresh_subtitle(output_dir):
    try:
        output_path = _resolve_output_dir(output_dir, must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "输出目录不存在"}), 404

    preferred_video_name = ""
    try:
        for item in history_service.read_unlocked():
            try:
                item_output_dir = _resolve_output_dir(item.get("output_dir"), must_exist=False)
            except ValueError:
                continue
            if item_output_dir.resolve(strict=False) == output_path.resolve(strict=False):
                preferred_video_name = str(item.get("video_name", "")).strip()
                break
    except Exception:
        preferred_video_name = ""

    output_media = _build_output_media_bundle(
        output_path,
        preferred_video_name=preferred_video_name,
    )
    video_name = str(output_media.get("video_file_name", "")).strip()
    if not video_name:
        return jsonify({"error": "未找到可重新解析的视频文件"}), 404

    video_path = (output_path / video_name).resolve(strict=False)
    try:
        _assert_within(video_path, output_path.resolve(strict=False), "video_file")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not video_path.exists() or not video_path.is_file():
        return jsonify({"error": "视频文件不存在"}), 404

    # 移走旧字幕导出文件，确保 generate_subtitles 不会直接命中旧 SRT。
    for path in output_path.glob(f"{video_path.stem}.*"):
        if path.suffix.lower() in {".srt", ".vtt", ".txt"} and path.is_file() and not path.is_symlink():
            try:
                backup_path = output_path / f"{path.name}.bak-{int(time.time())}"
                path.replace(backup_path)
            except OSError:
                try:
                    path.unlink()
                except OSError:
                    pass

    try:
        api_key, model_name, model_base_url = _read_shared_backend_model_options(require_api_key=True)
        whisper_model, _, _, _, _ = _normalize_processing_options({})
        agent = VideoAnalyzerAgent(
            api_key,
            whisper_model=whisper_model,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        fresh_cache_identity = f"{video_path.name}:manual-refresh:{time.time_ns()}"
        srt_path = agent.generate_subtitles(
            str(video_path),
            str(output_path),
            cache_identity=fresh_cache_identity,
        )
        subtitle_file = Path(srt_path)
        entries = _parse_srt_file_entries(subtitle_file)
        output_media = _build_output_media_bundle(output_path, preferred_srt_path=str(subtitle_file))
        return jsonify(
            {
                "success": True,
                "output_dir": str(output_path),
                "output_dir_name": output_path.name,
                "subtitle_file": subtitle_file.name,
                "line_count": len(entries),
                "truncated": False,
                "lines": entries[:12000],
                "video_preview_url": str(output_media.get("video_preview_url", "")).strip(),
                "subtitle_available": bool(output_media.get("subtitle_available", False)),
                "subtitle_exports": output_media.get("subtitle_exports", {}),
            }
        )
    except Exception as exc:
        logger.exception("重新解析字幕失败: %s", exc)
        return jsonify({"error": f"重新解析字幕失败：{exc}"}), 500


@app.route("/regenerate", methods=["POST"])
def regenerate_document():
    data = _json_payload()
    try:
        api_key, model_name, model_base_url = _read_shared_backend_model_options(
            require_api_key=True
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 503

    steps = data.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return jsonify({"error": "没有步骤数据"}), 400

    try:
        output_dir = _resolve_output_dir(data.get("output_dir"), must_exist=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"error": "输出目录不存在"}), 400

    raw_web_search = data.get("web_search")
    web_search = (
        _as_bool(raw_web_search)
        if raw_web_search is not None
        else _env_bool(("WEB_SEARCH", "web_search"), False)
    )

    try:
        agent = VideoAnalyzerAgent(
            api_key,
            model_name=model_name,
            model_base_url=model_base_url,
        )
        output_path = output_dir / "operation_guide.md"
        _run_async(
            agent.generate_step_document(
                steps=steps,
                output_path=str(output_path),
                srt_path=None,
                image_dir="images",
                web_search=web_search,
                respect_step_content=True,
            )
        )

        output_pdf = output_dir / "operation_guide.pdf"
        agent.generate_pdf(str(output_path), str(output_pdf))
        agent.save_results(steps, str(output_dir / "steps.json"))
        output_media = _build_output_media_bundle(output_dir)

        with open(output_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        return jsonify(
            {
                "success": True,
                "steps": steps,
                "markdown": md_content,
                "output_dir": str(output_dir),
                "output_dir_name": str(output_media.get("output_dir_name", "")).strip()
                or output_dir.name,
                "pdf_path": str(output_pdf),
                "video_preview_url": str(output_media.get("video_preview_url", "")).strip(),
                "subtitle_available": bool(output_media.get("subtitle_available", False)),
                "subtitle_file_name": str(output_media.get("subtitle_file_name", "")).strip(),
                "subtitle_line_count": _safe_int(
                    output_media.get("subtitle_line_count"), 0, 0
                ),
                "subtitle_exports": output_media.get("subtitle_exports", {}),
                "subtitle_workbench_url": str(
                    output_media.get("subtitle_workbench_url", "")
                ).strip(),
            }
        )
    except Exception as exc:
        error_message, status_code, normalized = _normalize_provider_error(
            exc, default_status=500
        )
        payload: Dict[str, Any] = {"error": error_message}
        if status_code >= 500 and not normalized:
            payload["trace"] = traceback.format_exc()
        return jsonify(payload), status_code


@app.route("/cleanup/<filename>")
def cleanup(filename):
    try:
        safe_name = secure_filename(filename)
        if not safe_name:
            return jsonify({"error": "文件名无效"}), 400

        upload_file_path = UPLOAD_ROOT / safe_name
        if upload_file_path.exists():
            upload_file_path.unlink()

        # 兼容旧目录命名: outputs/<stem>
        legacy_output_dir = OUTPUT_ROOT / Path(safe_name).stem
        if legacy_output_dir.exists() and legacy_output_dir.is_dir():
            shutil.rmtree(legacy_output_dir)

        # 新目录命名: outputs/<stem>_<timestamp>
        stem_prefix = secure_filename(Path(safe_name).stem)
        if stem_prefix:
            for output_dir in OUTPUT_ROOT.glob(f"{stem_prefix}_*"):
                if output_dir.is_dir():
                    shutil.rmtree(output_dir)

        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/history", methods=["GET"])
def get_history():
    owner_id = _ensure_history_owner()
    history = [_strip_owner_field(item) for item in load_history(owner_id)]
    return jsonify({"history": history})


@app.route("/history/<record_id>", methods=["GET"])
def get_history_record(record_id):
    owner_id = _ensure_history_owner()
    history = load_history(owner_id)
    for item in history:
        if item.get("id") != record_id:
            continue

        record = _strip_owner_field(item)
        output_dir_value = record.get("output_dir")
        if output_dir_value:
            try:
                output_dir = _resolve_output_dir(output_dir_value, must_exist=True)
            except (ValueError, FileNotFoundError):
                output_dir = None

            if output_dir:
                steps_path = output_dir / "steps.json"
                md_path = output_dir / "operation_guide.md"

                if steps_path.exists():
                    with open(steps_path, "r", encoding="utf-8") as f:
                        record["steps"] = json.load(f)
                if md_path.exists():
                    with open(md_path, "r", encoding="utf-8") as f:
                        record["markdown"] = f.read()
                output_media = _build_output_media_bundle(
                    output_dir,
                    preferred_video_name=str(record.get("video_name", "")).strip(),
                )
                record["output_dir_name"] = str(
                    output_media.get("output_dir_name", "")
                ).strip() or output_dir.name
                record["video_preview_url"] = str(
                    output_media.get("video_preview_url", "")
                ).strip()
                record["subtitle_available"] = bool(
                    output_media.get("subtitle_available", False)
                )
                record["subtitle_file_name"] = str(
                    output_media.get("subtitle_file_name", "")
                ).strip()
                record["subtitle_line_count"] = _safe_int(
                    output_media.get("subtitle_line_count"), 0, 0
                )
                record["subtitle_exports"] = output_media.get("subtitle_exports", {})
                record["subtitle_workbench_url"] = str(
                    output_media.get("subtitle_workbench_url", "")
                ).strip()

        return jsonify({"record": record})

    return jsonify({"error": "记录不存在"}), 404


@app.route("/history/<record_id>", methods=["DELETE"])
def delete_history(record_id):
    owner_id = _ensure_history_owner()
    try:
        delete_history_record(record_id, owner_id)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/upload_batch", methods=["POST"])
def upload_batch_files():
    if "files" not in request.files:
        return jsonify({"error": "没有文件"}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "没有选择文件"}), 400

    uploaded = []
    errors = []

    for file in files:
        if not file or file.filename == "":
            continue
        if not allowed_file(file.filename):
            errors.append(f"{file.filename}: 不支持的格式")
            continue

        staged_path = _build_upload_staging_path(file.filename)
        try:
            file.save(str(staged_path))
            if not is_valid_video_content(staged_path):
                _safe_remove_file(staged_path)
                errors.append(f"{file.filename}: 文件内容不是有效的视频格式")
                continue
            segment_policy = _build_video_segment_policy(staged_path)
            if bool(segment_policy.get("requires_trim")):
                _safe_remove_file(staged_path)
                errors.append(
                    (
                        f"{file.filename}: 属于裁剪优先区（"
                        f"{segment_policy.get('duration_text', '未知')} / "
                        f"{segment_policy.get('file_size_mb', 0)}MB），请先裁剪后再上传"
                    )
                )
                continue

            risk, file_fingerprint, risk_source = _run_upload_pre_risk_check(
                staged_video_path=staged_path,
                risk_agent=None,
                source="upload_batch",
            )
            if risk_source == "blacklist":
                _safe_remove_file(staged_path)
                errors.append(f"{file.filename}: 命中黑名单指纹拦截（完全一致视频）")
                continue

            if _is_risk_infra_failure(risk):
                _safe_remove_file(staged_path)
                payload, _ = _build_upload_risk_failure_response(risk)
                errors.append(f"{file.filename}: {str(payload.get('error', '上传风控服务不可用'))}")
                continue
            if _should_block_by_risk(str(risk.get("decision", ""))):
                blocked_hash = (
                    _register_blocked_video_fingerprint_by_hash(
                        file_fingerprint, risk, source="upload_batch_risk_block"
                    )
                    if file_fingerprint
                    else _register_blocked_video_fingerprint(
                        staged_path, risk, source="upload_batch_risk_block"
                    )
                )
                if blocked_hash:
                    risk["hash_sha256"] = blocked_hash
                _safe_remove_file(staged_path)
                errors.append(f"{file.filename}: {CONTENT_POLICY_BLOCK_MESSAGE}")
                continue

            save_path = _build_unique_upload_path(file.filename)
            shutil.move(str(staged_path), str(save_path))
            _mark_uploaded_video_loaded_now(save_path)
            uploaded.append(
                {
                    "filename": save_path.name,
                    "filepath": str(save_path),
                    "segment_policy": segment_policy,
                }
            )
        except Exception as exc:
            _safe_remove_file(staged_path)
            errors.append(f"{file.filename}: {str(exc)}")

    return jsonify({"uploaded": uploaded, "errors": errors, "total": len(files)})


@app.route("/batch_progress", methods=["GET"])
def get_batch_progress():
    owner_id = _ensure_history_owner()
    task_id = str(request.args.get("task_id", "")).strip()
    return jsonify(progress_state_service.get_batch_snapshot(owner_id, task_id=task_id))


@app.route("/single_progress", methods=["GET"])
def get_single_progress():
    owner_id = _ensure_history_owner()
    task_id = str(request.args.get("task_id", "")).strip()
    return jsonify(progress_state_service.get_single_snapshot(owner_id, task_id=task_id))


@app.route("/analyze_batch", methods=["POST"])
def analyze_batch():
    data = _json_payload()
    history_owner_id = _ensure_history_owner()
    task_id = _resolve_progress_task_id(data.get("task_id", data.get("progress_task_id", "")))
    try:
        api_key, model_name, model_base_url = _read_shared_backend_model_options(
            require_api_key=True
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "task_id": task_id}), 503

    raw_filepaths = data.get("filepaths", [])
    if not isinstance(raw_filepaths, list) or not raw_filepaths:
        return jsonify({"error": "没有视频文件", "task_id": task_id}), 400

    whisper_model, use_video, web_search, max_vision, fps = _normalize_processing_options(
        data
    )
    summary_only = _as_bool(data.get("summary_only", False))

    filepaths: List[Path] = []
    for raw_path in raw_filepaths:
        try:
            filepaths.append(_resolve_upload_filepath(raw_path))
        except ValueError as exc:
            return jsonify({"error": str(exc), "task_id": task_id}), 400
        except FileNotFoundError:
            return jsonify({"error": f"文件不存在: {raw_path}", "task_id": task_id}), 400

    file_segment_policies: List[Dict[str, Any]] = []
    file_segment_policy_map: Dict[str, Dict[str, Any]] = {}
    for path in filepaths:
        policy = _build_video_segment_policy(path)
        file_segment_policies.append(policy)
        file_segment_policy_map[str(path.resolve(strict=False))] = policy

    batch_segment_eval = _evaluate_batch_segment_policy(file_segment_policies)
    if not bool(batch_segment_eval.get("allowed", False)):
        reject_payload = {
            "error": str(batch_segment_eval.get("error", "")).strip() or "批量任务不符合分段策略",
            "code": str(batch_segment_eval.get("code", "")).strip()
            or "video_segment_batch_not_allowed",
            "batch_segment_policy": batch_segment_eval,
            "file_segment_policies": file_segment_policies,
            "task_id": task_id,
        }
        return (
            jsonify(reject_payload),
            400,
        )
    batch_policy_warnings = list(batch_segment_eval.get("warnings", []) or [])
    batch_workers = _resolve_batch_analyze_workers(
        total_files=len(filepaths),
    )

    _update_batch_progress(
        owner_id=history_owner_id,
        task_id=task_id,
        total=len(filepaths),
        current=0,
        status="processing",
        current_file="",
        stage="prepare",
        message=(
            f"批量任务已启动（并行度={batch_workers}），正在等待处理..."
            if not batch_policy_warnings
            else f"批量任务已启动（并行度={batch_workers}，策略提醒：{batch_policy_warnings[0]}）"
        ),
    )

    total_files = len(filepaths)
    results_by_index: Dict[int, Dict[str, Any]] = {}
    completed_counter = {"value": 0}
    completed_counter_lock = Lock()

    def _get_completed_count() -> int:
        with completed_counter_lock:
            return int(completed_counter["value"])

    def _mark_task_completed() -> int:
        with completed_counter_lock:
            completed_counter["value"] = int(completed_counter["value"]) + 1
            return int(completed_counter["value"])

    def _analyze_single_batch_file(idx: int, filepath: Path) -> Tuple[int, Dict[str, Any], str, str]:
        filepath_key = str(filepath.resolve(strict=False))
        segment_policy = file_segment_policy_map.get(filepath_key) or _build_video_segment_policy(
            filepath
        )
        (
            effective_use_video,
            effective_web_search,
            effective_max_vision,
            effective_summary_only,
            segment_guardrails,
        ) = _apply_video_segment_processing_guardrails(
            segment_policy,
            use_video=use_video,
            web_search=web_search,
            max_vision=max_vision,
            summary_only=summary_only,
        )

        _update_batch_progress(
            owner_id=history_owner_id,
            task_id=task_id,
            current=_get_completed_count(),
            current_file=filepath.name,
            stage="prepare",
            message=f"正在准备处理: {filepath.name}",
        )

        def _batch_progress_callback(stage: str, message: str, *, _name=filepath.name) -> None:
            _update_batch_progress(
                owner_id=history_owner_id,
                task_id=task_id,
                current=_get_completed_count(),
                current_file=_name,
                stage=stage,
                message=message,
            )

        try:
            steps, md_content, output_dir, output_pdf, has_steps, result_meta = process_video(
                filepath,
                api_key,
                whisper_model,
                model_name,
                model_base_url,
                effective_use_video,
                effective_web_search,
                effective_max_vision,
                fps,
                summary_only=effective_summary_only,
                history_owner_id=history_owner_id,
                progress_callback=_batch_progress_callback,
            )
            result_meta["segment_policy"] = segment_policy
            if segment_guardrails:
                result_meta["segment_guardrails"] = segment_guardrails
            output_media = (
                result_meta.get("output_media", {})
                if isinstance(result_meta.get("output_media", {}), dict)
                else {}
            )

            if not has_steps:
                return (
                    idx,
                    {
                        "index": idx,
                        "filename": filepath.name,
                        "success": False,
                        "error": "未生成有效分析内容",
                        "result_mode": str(result_meta.get("result_mode", "empty")),
                        "fallback_used": bool(result_meta.get("fallback_used", False)),
                        "analysis_note": str(result_meta.get("analysis_note", "")).strip(),
                        "quality_score": _safe_float(result_meta.get("quality_score", 0.0), 0.0, 0.0, 1.0),
                        "degrade_reason": str(result_meta.get("degrade_reason", "")).strip(),
                        "content_title": str(result_meta.get("content_title", "")).strip(),
                        "key_points": result_meta.get("key_points", []),
                        "timeline_points": result_meta.get("timeline_points", []),
                        "confidence_note": str(result_meta.get("confidence_note", "")).strip(),
                        "segment_policy": segment_policy,
                        "segment_guardrails": segment_guardrails,
                        "output_dir_name": str(
                            output_media.get("output_dir_name", "")
                        ).strip()
                        or Path(output_dir).name,
                        "video_preview_url": str(
                            output_media.get("video_preview_url", "")
                        ).strip(),
                        "subtitle_available": bool(
                            output_media.get("subtitle_available", False)
                        ),
                        "subtitle_file_name": str(
                            output_media.get("subtitle_file_name", "")
                        ).strip(),
                        "subtitle_line_count": _safe_int(
                            output_media.get("subtitle_line_count"), 0, 0
                        ),
                        "subtitle_exports": output_media.get("subtitle_exports", {}),
                        "subtitle_workbench_url": str(
                            output_media.get("subtitle_workbench_url", "")
                        ).strip(),
                        "effective_options": {
                            "use_video": effective_use_video,
                            "web_search": effective_web_search,
                            "max_vision": effective_max_vision,
                            "summary_only": effective_summary_only,
                        },
                    },
                    "failed",
                    "未能识别到操作步骤",
                )

            return (
                idx,
                {
                    "index": idx,
                    "filename": filepath.name,
                    "success": True,
                    "steps_count": len(steps) if steps else 0,
                    "output_dir": output_dir,
                    "output_dir_name": str(output_media.get("output_dir_name", "")).strip()
                    or Path(output_dir).name,
                    "pdf_path": output_pdf,
                    "markdown": md_content,
                    "steps": steps,
                    "result_mode": str(result_meta.get("result_mode", "steps")),
                    "fallback_used": bool(result_meta.get("fallback_used", False)),
                    "analysis_note": str(result_meta.get("analysis_note", "")).strip(),
                    "quality_score": _safe_float(result_meta.get("quality_score", 0.0), 0.0, 0.0, 1.0),
                    "degrade_reason": str(result_meta.get("degrade_reason", "")).strip(),
                    "content_title": str(result_meta.get("content_title", "")).strip(),
                    "key_points": result_meta.get("key_points", []),
                    "timeline_points": result_meta.get("timeline_points", []),
                    "confidence_note": str(result_meta.get("confidence_note", "")).strip(),
                    "segment_policy": segment_policy,
                    "segment_guardrails": segment_guardrails,
                    "video_preview_url": str(
                        output_media.get("video_preview_url", "")
                    ).strip(),
                    "subtitle_available": bool(
                        output_media.get("subtitle_available", False)
                    ),
                    "subtitle_file_name": str(
                        output_media.get("subtitle_file_name", "")
                    ).strip(),
                    "subtitle_line_count": _safe_int(
                        output_media.get("subtitle_line_count"), 0, 0
                    ),
                    "subtitle_exports": output_media.get("subtitle_exports", {}),
                    "subtitle_workbench_url": str(
                        output_media.get("subtitle_workbench_url", "")
                    ).strip(),
                    "effective_options": {
                        "use_video": effective_use_video,
                        "web_search": effective_web_search,
                        "max_vision": effective_max_vision,
                        "summary_only": effective_summary_only,
                    },
                },
                "done",
                (
                    f"{filepath.name} 分析完成（候选内容）"
                    if result_meta.get("fallback_used")
                    else f"{filepath.name} 分析完成"
                ),
            )
        except ContentPolicyBlockedError as exc:
            blocked_notice = _build_blocked_notice_payload(exc.risk)
            return (
                idx,
                {
                    "index": idx,
                    "filename": filepath.name,
                    "success": False,
                    "error": str(exc),
                    "code": "content_policy_violation",
                    "risk": exc.risk,
                    "result_mode": "blocked_notice",
                    "quality_score": 0.0,
                    "degrade_reason": "content_policy_blocked",
                    "blocked_notice": blocked_notice,
                    "segment_policy": segment_policy,
                },
                "moderation",
                str(exc),
            )
        except Exception as exc:
            error_msg, _, _ = _normalize_provider_error(exc, default_status=500)
            return (
                idx,
                {
                    "index": idx,
                    "filename": filepath.name,
                    "success": False,
                    "error": error_msg,
                    "segment_policy": segment_policy,
                },
                "failed",
                error_msg,
            )

    try:
        with ThreadPoolExecutor(max_workers=batch_workers) as executor:
            future_map = {
                executor.submit(_analyze_single_batch_file, idx, filepath): (idx, filepath)
                for idx, filepath in enumerate(filepaths, start=1)
            }
            for future in as_completed(future_map):
                idx, filepath = future_map[future]
                try:
                    result_idx, result_payload, final_stage, final_message = future.result()
                except Exception as exc:
                    error_msg, _, _ = _normalize_provider_error(exc, default_status=500)
                    result_idx = idx
                    result_payload = {
                        "index": idx,
                        "filename": filepath.name,
                        "success": False,
                        "error": error_msg,
                    }
                    final_stage = "failed"
                    final_message = error_msg

                results_by_index[result_idx] = result_payload
                completed_count = _mark_task_completed()
                _update_batch_progress(
                    owner_id=history_owner_id,
                    task_id=task_id,
                    current=completed_count,
                    current_file=filepath.name,
                    stage=final_stage,
                    message=f"已完成 {completed_count}/{total_files}：{final_message}",
                )
    finally:
        _update_batch_progress(
            owner_id=history_owner_id,
            task_id=task_id,
            status="completed",
            current_file="",
            stage="done",
            message="\u6279\u91cf\u5206\u6790\u5df2\u5b8c\u6210",
        )

    results = [results_by_index[idx] for idx in sorted(results_by_index)]
    success_count = sum(1 for r in results if r.get("success"))
    return jsonify(
        {
            "success": True,
            "results": results,
            "batch_segment_policy": batch_segment_eval,
            "batch_policy_warnings": batch_policy_warnings,
            "batch_parallel_workers": batch_workers,
            "task_id": task_id,
            "summary": {
                "total": len(filepaths),
                "success": success_count,
                "failed": len(filepaths) - success_count,
            },
        }
    )


@app.route("/download_batch_zip", methods=["POST"])
def download_batch_zip():
    data = _json_payload()
    output_dirs = data.get("output_dirs", [])
    if not isinstance(output_dirs, list) or not output_dirs:
        return jsonify({"error": "没有输出目录"}), 400

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for raw_output_dir in output_dirs:
            try:
                output_path = _resolve_output_dir(raw_output_dir, must_exist=True)
            except (ValueError, FileNotFoundError):
                continue

            base_name = output_path.name
            _append_output_bundle_to_zip(zf, output_path, prefix=f"{base_name}/")

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="batch_results.zip",
    )


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes"}
    host = str(os.getenv("HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = _safe_int(os.getenv("PORT"), 5000, 1, 65535)
    if (not debug_mode) or os.getenv("WERKZEUG_RUN_MAIN", "").strip().lower() in {"1", "true"}:
        _start_upload_video_auto_cleanup()
        _start_history_retention_cleanup()
    if debug_mode:
        app.run(debug=True, host=host, port=port)
    else:
        from waitress import serve

        waitress_threads = _safe_int(os.getenv("WAITRESS_THREADS"), 4, 1, 64)
        waitress_connection_limit = _safe_int(
            os.getenv("WAITRESS_CONNECTION_LIMIT"), 100, 1, 10000
        )
        logger.info(
            "Starting production server with Waitress: host=%s port=%s threads=%s connection_limit=%s",
            host,
            port,
            waitress_threads,
            waitress_connection_limit,
        )
        serve(
            app,
            host=host,
            port=port,
            threads=waitress_threads,
            connection_limit=waitress_connection_limit,
        )
