"""Centralized configuration for the video-to-doc backend.

Environment variables are loaded once here, then exposed as module-level
constants. Importing this module also ensures the required runtime
directories exist (preserving the original startup side effects).
"""

import os
import re
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = (PROJECT_ROOT / "uploads").resolve()
OUTPUT_ROOT = (PROJECT_ROOT / "outputs").resolve()
HISTORY_PATH = (PROJECT_ROOT / "history.json").resolve()
UPLOAD_SESSION_ROOT = (UPLOAD_ROOT / ".upload_sessions").resolve()


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.getenv(name, "")).strip()
    if not raw_value:
        return int(default)
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, "")).strip()
    if not raw_value:
        return float(default)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return float(default)


def _env_text(names: Tuple[str, ...], default: str = "") -> str:
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None:
            continue
        text = str(raw_value).strip()
        if text:
            return text
    return str(default)


def _env_bool(names: Tuple[str, ...], default: bool = False) -> bool:
    raw_value = _env_text(names, "")
    if not raw_value:
        return bool(default)
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


_analysis_task_db_value = _env_text(
    ("ANALYSIS_TASK_DB_PATH",),
    str(UPLOAD_ROOT / ".analysis_tasks.sqlite3"),
)
_analysis_task_db_candidate = Path(_analysis_task_db_value).expanduser()
if not _analysis_task_db_candidate.is_absolute():
    _analysis_task_db_candidate = UPLOAD_ROOT / _analysis_task_db_candidate
ANALYSIS_TASK_DB_PATH = _analysis_task_db_candidate.resolve()
ANALYSIS_TASK_MAX_WORKERS = max(1, min(32, _env_int("ANALYSIS_TASK_MAX_WORKERS", 2)))
ANALYSIS_TASK_POLL_INTERVAL_SECONDS = max(
    0.01, _env_float("ANALYSIS_TASK_POLL_INTERVAL_SECONDS", 0.25)
)
ANALYSIS_TASK_STALE_AFTER_SECONDS = max(
    0.0, _env_float("ANALYSIS_TASK_STALE_AFTER_SECONDS", 300.0)
)


ALLOWED_EXTENSIONS = {
    "mp4",
    "avi",
    "mov",
    "mkv",
    "wmv",
    "flv",
    "webm",
    "m4v",
    "mpg",
    "mpeg",
    "3gp",
    "ts",
    "m2ts",
}
ALLOWED_WHISPER_MODELS = {"tiny", "base", "small", "medium", "large"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


MAX_HISTORY = 50
MAX_VISION_CALLS = 10
FPS_MIN = 0.1
FPS_MAX = 10.0
DEFAULT_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
MAX_UPLOAD_CHUNK_SIZE = 32 * 1024 * 1024
UPLOAD_IN_MEMORY_MAX_FILE_SIZE = 64 * 1024 * 1024
UPLOAD_IN_MEMORY_MAX_TOTAL_BYTES = 256 * 1024 * 1024
# 模型配置一律以 .env 为准，绝不写死模型名称/地址。
# 未在 .env 中配置时，这里解析为空字符串，由调用方在使用时报错并提示前端补全配置。
# 注意：本项目的视觉风控 / 视频理解依赖「视觉模型（支持图片输入）」，
# 请在 .env 的 MODEL_NAME 填写具备视觉能力的模型。
DEFAULT_MODEL_NAME = _env_text(("MODEL_NAME", "RISK_FALLBACK_MODEL_NAME"), "")
DEFAULT_MODEL_BASE_URL = _env_text(("MODEL_BASE_URL", "RISK_FALLBACK_MODEL_BASE_URL"), "")
# 联网搜索开通引导链接：纯前端提示用途，可在 .env 覆盖；留空则不展示引导链接。
WEB_SEARCH_ACTIVATION_URL = _env_text(("WEB_SEARCH_ACTIVATION_URL",), "")
RISK_MAX_FRAMES = max(1, _env_int("RISK_MAX_FRAMES", 4))
RISK_MIN_FRAMES = max(1, min(3, RISK_MAX_FRAMES))
RISK_DYNAMIC_MAX_FRAMES = max(RISK_MAX_FRAMES, _env_int("RISK_DYNAMIC_MAX_FRAMES", 8))
RISK_FRAME_GROWTH_START_SECONDS = 20
RISK_FRAME_GROWTH_EVERY_SECONDS = 45
RISK_BLOCK_THRESHOLD = 0.8
RISK_RESTRICT_THRESHOLD = 0.55
RISK_BLOCK_ON_RESTRICT = True
RISK_DIMENSION_HARD_BLOCK_SCORE = 0.72
RISK_CRITICAL_SCORE = 0.9
CONTENT_POLICY_BLOCK_MESSAGE = (
    "上传已被风控强拦截：检测到高风险色情/裸露/血腥/暴力内容，"
    "系统已直接拒绝该视频上传。请删除敏感画面后重试"
)
TEXT_RISK_BLOCK_THRESHOLD = 0.78
TEXT_RISK_RESTRICT_THRESHOLD = 0.5
FALLBACK_CANDIDATE_MAX_STEPS = 5
FALLBACK_MIN_STEPS = 3
QUALITY_MODE_PRIOR: Dict[str, float] = {
    "steps": 0.78,
    "candidate_steps": 0.5,
    "timeline_summary": 0.34,
    "blocked_notice": 0.0,
}
QUALITY_MODE_CAP: Dict[str, float] = {
    "steps": 0.98,
    "candidate_steps": 0.72,
    "timeline_summary": 0.56,
    "blocked_notice": 0.0,
}
QUALITY_REASON_PENALTY_MAP: Dict[str, float] = {
    "standard_steps_not_detected_subtitle_candidates_generated": 0.09,
    "subtitle_signal_insufficient_timeline_summary_generated": 0.14,
    "user_requested_summary_only": 0.03,
    "content_generation_failed_emergency_summary_generated": 0.18,
    "content_generation_failed": 0.22,
    "content_policy_blocked": 1.0,
}
QUALITY_SOURCE_WEIGHT_MAP: Dict[str, float] = {
    "manual": 0.95,
    "manual_edit": 0.95,
    "vision": 0.9,
    "vision_enhanced": 0.9,
    "video": 0.84,
    "subtitle": 0.8,
    "model": 0.8,
    "subtitle_candidate": 0.52,
    "timeline_summary": 0.35,
    "fallback_padding": 0.22,
}
ENV_FILE_PATH = (PROJECT_ROOT / ".env").resolve()
RISK_FALLBACK_ENV_BLOCK_MARKER = "# ===== 风控视觉兜底（仅系统管理员） ====="
RISK_FALLBACK_ENV_BLOCK_MARKER_LEGACY = "# ===== RISK VISUAL FALLBACK (SYSTEM ADMIN ONLY) ====="
RISK_FALLBACK_ENV_KEYS = (
    "RISK_FALLBACK_API_KEY",
    "RISK_FALLBACK_MODEL_NAME",
    "RISK_FALLBACK_MODEL_BASE_URL",
)
HISTORY_OWNER_HEADER = "X-Client-ID"
HISTORY_OWNER_COOKIE = "video_insights_client_id"
HISTORY_OWNER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2
HISTORY_OWNER_MAX_LEN = 120
HISTORY_OWNER_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
QUARANTINE_ROOT = (UPLOAD_ROOT / ".quarantine").resolve()
UPLOAD_STAGING_ROOT = (UPLOAD_ROOT / ".staging").resolve()
RISK_KEYWORD_LEXICON_PATH = (PROJECT_ROOT / "risk_keyword_lexicon.json").resolve()
RISK_BLOCKLIST_PATH = (UPLOAD_ROOT / ".risk_blocklist.json").resolve()
RISK_RESULT_CACHE_PATH = (UPLOAD_ROOT / ".risk_result_cache.json").resolve()
RISK_RESULT_CACHE_TTL_SECONDS = 60 * 60 * 24
RISK_RESULT_CACHE_MAX_ENTRIES = 500
HISTORY_RETENTION_TTL_SECONDS = 72 * 60 * 60
HISTORY_RETENTION_SCAN_INTERVAL_SECONDS = 60 * 30
UPLOAD_VIDEO_AUTO_DELETE_TTL_SECONDS = 60 * 60 * 24
UPLOAD_VIDEO_AUTO_DELETE_SCAN_INTERVAL_SECONDS = 60 * 30
LONG_VIDEO_PREPROCESS_ENABLED = (
    str(os.getenv("LONG_VIDEO_PREPROCESS_ENABLED", "1")).strip().lower()
    in {"1", "true", "yes", "on"}
)
LONG_VIDEO_PREPROCESS_MIN_DURATION_SECONDS = 20 * 60
LONG_VIDEO_PREPROCESS_MIN_FILE_SIZE_MB = 250
LONG_VIDEO_PREPROCESS_SLICE_SECONDS = 8 * 60
LONG_VIDEO_PREPROCESS_MAX_SLICES = 24
LONG_VIDEO_PREPROCESS_MAX_WIDTH = 960
LONG_VIDEO_PREPROCESS_TARGET_FPS = 12
LONG_VIDEO_PREPROCESS_CRF = 30
LONG_VIDEO_PREPROCESS_PRESET = "veryfast"
LONG_VIDEO_PREPROCESS_AUDIO_BITRATE = "64k"
# Web-friendly preview transcode for the result-page subtitle workbench player.
# Generates an H.264 + faststart copy (moov atom at the front) so seeking and
# playback stay smooth even when the source is high-bitrate/high-resolution.
WEB_PREVIEW_ENABLED = (
    str(os.getenv("WEB_PREVIEW_ENABLED", "1")).strip().lower()
    in {"1", "true", "yes", "on"}
)
WEB_PREVIEW_BASENAME = "web_preview.mp4"
# Longest edge cap (px); 1280 keeps 720p landscape / portrait equivalents.
WEB_PREVIEW_MAX_LONG_EDGE = int(os.getenv("WEB_PREVIEW_MAX_LONG_EDGE", "1280"))
WEB_PREVIEW_CRF = int(os.getenv("WEB_PREVIEW_CRF", "26"))
WEB_PREVIEW_PRESET = str(os.getenv("WEB_PREVIEW_PRESET", "veryfast")).strip() or "veryfast"
WEB_PREVIEW_AUDIO_BITRATE = str(os.getenv("WEB_PREVIEW_AUDIO_BITRATE", "128k")).strip() or "128k"
# Skip re-encoding for tiny sources that already play smoothly (falls back to original).
WEB_PREVIEW_SKIP_BELOW_MB = float(os.getenv("WEB_PREVIEW_SKIP_BELOW_MB", "6"))
VIDEO_SEGMENT_STANDARD_MAX_DURATION_SECONDS = 20 * 60
VIDEO_SEGMENT_LONG_MAX_DURATION_SECONDS = 45 * 60
VIDEO_SEGMENT_SUPER_LONG_MAX_DURATION_SECONDS = 90 * 60
VIDEO_SEGMENT_STANDARD_MAX_SIZE_MB = 250.0
VIDEO_SEGMENT_CROP_REQUIRED_MIN_SIZE_MB = 500.0
VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_FILES = 5
VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_TOTAL_DURATION_SECONDS = 60 * 60
VIDEO_SEGMENT_BATCH_LONG_MAX_FILES = 2
BATCH_ANALYZE_MAX_WORKERS = max(1, min(16, _env_int("BATCH_ANALYZE_MAX_WORKERS", 2)))
SCRAPE_FETCH_MODE = _env_text(("SCRAPE_FETCH_MODE", "scrape_fetch_mode"), "auto").strip().lower()
if SCRAPE_FETCH_MODE not in {"auto", "static", "dynamic"}:
    SCRAPE_FETCH_MODE = "auto"
SCRAPE_TIMEOUT_SECONDS = max(5, min(120, _env_int("SCRAPE_TIMEOUT_SECONDS", 45)))
SCRAPE_RETRIES = max(0, min(5, _env_int("SCRAPE_RETRIES", 3)))
SCRAPE_RETRY_DELAY_SECONDS = max(0, min(20, _env_int("SCRAPE_RETRY_DELAY_SECONDS", 2)))
SCRAPE_DYNAMIC_WAIT_SECONDS = max(0, min(20, _env_int("SCRAPE_DYNAMIC_WAIT_SECONDS", 4)))
SCRAPE_DYNAMIC_HEADLESS = _env_bool(("SCRAPE_DYNAMIC_HEADLESS", "scrape_dynamic_headless"), True)
SCRAPE_DYNAMIC_DISABLE_RESOURCES = _env_bool(
    ("SCRAPE_DYNAMIC_DISABLE_RESOURCES", "scrape_dynamic_disable_resources"), False
)
SCRAPE_DYNAMIC_NETWORK_IDLE = _env_bool(
    ("SCRAPE_DYNAMIC_NETWORK_IDLE", "scrape_dynamic_network_idle"), True
)
SCRAPE_IMPERSONATE = _env_text(("SCRAPE_IMPERSONATE", "scrape_impersonate"), "chrome")
SCRAPE_PROXY_URL = _env_text(("SCRAPE_PROXY_URL", "scrape_proxy_url"), "")
SCRAPE_USER_AGENT = _env_text(("SCRAPE_USER_AGENT", "scrape_user_agent"), "")
SCRAPE_EXTRA_HEADERS_JSON = _env_text(
    ("SCRAPE_EXTRA_HEADERS_JSON", "scrape_extra_headers_json"), ""
)
SCRAPE_COOKIES_JSON = _env_text(("SCRAPE_COOKIES_JSON", "scrape_cookies_json"), "")
SCRAPE_MODEL_PARSE_ENABLED = _env_bool(
    ("SCRAPE_MODEL_PARSE_ENABLED", "scrape_model_parse_enabled"), True
)
SCRAPE_MODEL_HTML_MAX_CHARS = max(4000, min(120000, _env_int("SCRAPE_MODEL_HTML_MAX_CHARS", 32000)))
SCRAPE_STRICT_MEDIA_ID_MATCH = _env_bool(
    ("SCRAPE_STRICT_MEDIA_ID_MATCH", "scrape_strict_media_id_match"), True
)
SCRAPE_STEALTH_SESSION_MAX_PAGES = max(
    1, min(8, _env_int("SCRAPE_STEALTH_SESSION_MAX_PAGES", 2))
)
SCRAPE_STEALTH_SESSION_MAX_REQUESTS = max(
    1, min(500, _env_int("SCRAPE_STEALTH_SESSION_MAX_REQUESTS", 60))
)
SCRAPE_STEALTH_SESSION_IDLE_TTL_SECONDS = max(
    30, min(3600, _env_int("SCRAPE_STEALTH_SESSION_IDLE_TTL_SECONDS", 300))
)
SCRAPE_STEALTH_REAL_CHROME = _env_bool(
    ("SCRAPE_STEALTH_REAL_CHROME", "scrape_stealth_real_chrome"), False
)
SCRAPE_STEALTH_BLOCK_WEBRTC = _env_bool(
    ("SCRAPE_STEALTH_BLOCK_WEBRTC", "scrape_stealth_block_webrtc"), True
)
SCRAPE_STEALTH_SOLVE_CLOUDFLARE = _env_bool(
    ("SCRAPE_STEALTH_SOLVE_CLOUDFLARE", "scrape_stealth_solve_cloudflare"), False
)
SCRAPE_STEALTH_LOCALE = _env_text(("SCRAPE_STEALTH_LOCALE", "scrape_stealth_locale"), "")
SCRAPE_STEALTH_TIMEZONE_ID = _env_text(
    ("SCRAPE_STEALTH_TIMEZONE_ID", "scrape_stealth_timezone_id"), ""
)
YTDLP_PREFER_BROWSER_COOKIES = _env_bool(
    ("YTDLP_PREFER_BROWSER_COOKIES", "ytdlp_prefer_browser_cookies"), True
)
YTDLP_COOKIES_FROM_BROWSER = _env_text(
    ("YTDLP_COOKIES_FROM_BROWSER", "ytdlp_cookies_from_browser"), ""
)
YTDLP_BROWSER_FALLBACKS = _env_text(
    ("YTDLP_BROWSER_FALLBACKS", "ytdlp_browser_fallbacks"), "chrome,edge"
)
YTDLP_COOKIES_FILE = _env_text(("YTDLP_COOKIES_FILE", "ytdlp_cookies_file"), "")
YTDLP_COOKIE_HEADER = _env_text(("YTDLP_COOKIE_HEADER", "ytdlp_cookie_header"), "")

# SSRF 防护：是否允许 URL 导入访问内网/保留地址（默认禁止）。
# 仅在明确信任的内网部署场景才设为 1，避免被用于探测云元数据/内网服务。
URL_IMPORT_ALLOW_PRIVATE_HOSTS = _env_bool(
    ("URL_IMPORT_ALLOW_PRIVATE_HOSTS", "url_import_allow_private_hosts"), False
)

UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_SESSION_ROOT.mkdir(parents=True, exist_ok=True)
QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_STAGING_ROOT.mkdir(parents=True, exist_ok=True)


__all__ = [
    "PROJECT_ROOT",
    "UPLOAD_ROOT",
    "OUTPUT_ROOT",
    "HISTORY_PATH",
    "UPLOAD_SESSION_ROOT",
    "_env_int",
    "_env_float",
    "_env_text",
    "_env_bool",
    "ANALYSIS_TASK_DB_PATH",
    "ANALYSIS_TASK_MAX_WORKERS",
    "ANALYSIS_TASK_POLL_INTERVAL_SECONDS",
    "ANALYSIS_TASK_STALE_AFTER_SECONDS",
    "ALLOWED_EXTENSIONS",
    "ALLOWED_WHISPER_MODELS",
    "allowed_file",
    "MAX_HISTORY",
    "MAX_VISION_CALLS",
    "FPS_MIN",
    "FPS_MAX",
    "DEFAULT_UPLOAD_CHUNK_SIZE",
    "MAX_UPLOAD_CHUNK_SIZE",
    "UPLOAD_IN_MEMORY_MAX_FILE_SIZE",
    "UPLOAD_IN_MEMORY_MAX_TOTAL_BYTES",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_BASE_URL",
    "WEB_SEARCH_ACTIVATION_URL",
    "RISK_MAX_FRAMES",
    "RISK_MIN_FRAMES",
    "RISK_DYNAMIC_MAX_FRAMES",
    "RISK_FRAME_GROWTH_START_SECONDS",
    "RISK_FRAME_GROWTH_EVERY_SECONDS",
    "RISK_BLOCK_THRESHOLD",
    "RISK_RESTRICT_THRESHOLD",
    "RISK_BLOCK_ON_RESTRICT",
    "RISK_DIMENSION_HARD_BLOCK_SCORE",
    "RISK_CRITICAL_SCORE",
    "CONTENT_POLICY_BLOCK_MESSAGE",
    "TEXT_RISK_BLOCK_THRESHOLD",
    "TEXT_RISK_RESTRICT_THRESHOLD",
    "FALLBACK_CANDIDATE_MAX_STEPS",
    "FALLBACK_MIN_STEPS",
    "QUALITY_MODE_PRIOR",
    "QUALITY_MODE_CAP",
    "QUALITY_REASON_PENALTY_MAP",
    "QUALITY_SOURCE_WEIGHT_MAP",
    "ENV_FILE_PATH",
    "RISK_FALLBACK_ENV_BLOCK_MARKER",
    "RISK_FALLBACK_ENV_BLOCK_MARKER_LEGACY",
    "RISK_FALLBACK_ENV_KEYS",
    "HISTORY_OWNER_HEADER",
    "HISTORY_OWNER_COOKIE",
    "HISTORY_OWNER_COOKIE_MAX_AGE",
    "HISTORY_OWNER_MAX_LEN",
    "HISTORY_OWNER_PATTERN",
    "QUARANTINE_ROOT",
    "UPLOAD_STAGING_ROOT",
    "RISK_KEYWORD_LEXICON_PATH",
    "RISK_BLOCKLIST_PATH",
    "RISK_RESULT_CACHE_PATH",
    "RISK_RESULT_CACHE_TTL_SECONDS",
    "RISK_RESULT_CACHE_MAX_ENTRIES",
    "HISTORY_RETENTION_TTL_SECONDS",
    "HISTORY_RETENTION_SCAN_INTERVAL_SECONDS",
    "UPLOAD_VIDEO_AUTO_DELETE_TTL_SECONDS",
    "UPLOAD_VIDEO_AUTO_DELETE_SCAN_INTERVAL_SECONDS",
    "LONG_VIDEO_PREPROCESS_ENABLED",
    "LONG_VIDEO_PREPROCESS_MIN_DURATION_SECONDS",
    "LONG_VIDEO_PREPROCESS_MIN_FILE_SIZE_MB",
    "LONG_VIDEO_PREPROCESS_SLICE_SECONDS",
    "LONG_VIDEO_PREPROCESS_MAX_SLICES",
    "LONG_VIDEO_PREPROCESS_MAX_WIDTH",
    "LONG_VIDEO_PREPROCESS_TARGET_FPS",
    "LONG_VIDEO_PREPROCESS_CRF",
    "LONG_VIDEO_PREPROCESS_PRESET",
    "LONG_VIDEO_PREPROCESS_AUDIO_BITRATE",
    "WEB_PREVIEW_ENABLED",
    "WEB_PREVIEW_BASENAME",
    "WEB_PREVIEW_MAX_LONG_EDGE",
    "WEB_PREVIEW_CRF",
    "WEB_PREVIEW_PRESET",
    "WEB_PREVIEW_AUDIO_BITRATE",
    "WEB_PREVIEW_SKIP_BELOW_MB",
    "VIDEO_SEGMENT_STANDARD_MAX_DURATION_SECONDS",
    "VIDEO_SEGMENT_LONG_MAX_DURATION_SECONDS",
    "VIDEO_SEGMENT_SUPER_LONG_MAX_DURATION_SECONDS",
    "VIDEO_SEGMENT_STANDARD_MAX_SIZE_MB",
    "VIDEO_SEGMENT_CROP_REQUIRED_MIN_SIZE_MB",
    "VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_FILES",
    "VIDEO_SEGMENT_BATCH_STANDARD_RECOMMENDED_MAX_TOTAL_DURATION_SECONDS",
    "VIDEO_SEGMENT_BATCH_LONG_MAX_FILES",
    "BATCH_ANALYZE_MAX_WORKERS",
    "SCRAPE_FETCH_MODE",
    "SCRAPE_TIMEOUT_SECONDS",
    "SCRAPE_RETRIES",
    "SCRAPE_RETRY_DELAY_SECONDS",
    "SCRAPE_DYNAMIC_WAIT_SECONDS",
    "SCRAPE_DYNAMIC_HEADLESS",
    "SCRAPE_DYNAMIC_DISABLE_RESOURCES",
    "SCRAPE_DYNAMIC_NETWORK_IDLE",
    "SCRAPE_IMPERSONATE",
    "SCRAPE_PROXY_URL",
    "SCRAPE_USER_AGENT",
    "SCRAPE_EXTRA_HEADERS_JSON",
    "SCRAPE_COOKIES_JSON",
    "SCRAPE_MODEL_PARSE_ENABLED",
    "SCRAPE_MODEL_HTML_MAX_CHARS",
    "SCRAPE_STRICT_MEDIA_ID_MATCH",
    "SCRAPE_STEALTH_SESSION_MAX_PAGES",
    "SCRAPE_STEALTH_SESSION_MAX_REQUESTS",
    "SCRAPE_STEALTH_SESSION_IDLE_TTL_SECONDS",
    "SCRAPE_STEALTH_REAL_CHROME",
    "SCRAPE_STEALTH_BLOCK_WEBRTC",
    "SCRAPE_STEALTH_SOLVE_CLOUDFLARE",
    "SCRAPE_STEALTH_LOCALE",
    "SCRAPE_STEALTH_TIMEZONE_ID",
    "YTDLP_PREFER_BROWSER_COOKIES",
    "YTDLP_COOKIES_FROM_BROWSER",
    "YTDLP_BROWSER_FALLBACKS",
    "YTDLP_COOKIES_FILE",
    "YTDLP_COOKIE_HEADER",
    "URL_IMPORT_ALLOW_PRIVATE_HOSTS",
]
