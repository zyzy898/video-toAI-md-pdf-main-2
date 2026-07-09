import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from werkzeug.utils import secure_filename


def _normalized_allowed_extensions(allowed_extensions: set[str] | frozenset[str]) -> set[str]:
    return {str(extension).strip().lower().lstrip(".") for extension in allowed_extensions if extension}


def safe_video_filename(
    raw_name: str,
    fallback_stem: str = "url_video",
    *,
    allowed_extensions: set[str] | frozenset[str],
) -> str:
    """Return a filesystem-safe video filename with an allowed extension."""
    allowed = _normalized_allowed_extensions(allowed_extensions)
    safe_name = secure_filename(str(raw_name or "").strip())
    fallback = secure_filename(fallback_stem) or "url_video"
    stem = secure_filename(Path(safe_name).stem) if safe_name else fallback
    if not stem:
        stem = fallback

    suffix = Path(safe_name).suffix.lower() if safe_name else ""
    if not suffix or suffix.lstrip(".") not in allowed:
        suffix = ".mp4"
    return f"{stem}{suffix}"


def extract_filename_from_content_disposition(header_value: str) -> str:
    """Extract a filename from Content-Disposition, including RFC 5987 filename*."""
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


def guess_video_filename_from_url(
    raw_url: str,
    content_disposition: str = "",
    content_type: str = "",
    fallback: str = "url_video.mp4",
    *,
    allowed_extensions: set[str] | frozenset[str],
) -> str:
    """Infer a safe video filename from headers, URL path, or content type."""
    allowed = _normalized_allowed_extensions(allowed_extensions)
    candidate = extract_filename_from_content_disposition(content_disposition)
    if not candidate:
        parsed = urlparse(raw_url)
        candidate = unquote(Path(parsed.path).name)

    safe_candidate = secure_filename(candidate)
    stem = secure_filename(Path(safe_candidate).stem) if safe_candidate else ""
    suffix = Path(safe_candidate).suffix.lower() if safe_candidate else ""
    if stem and suffix and suffix.lstrip(".") in allowed:
        return f"{stem}{suffix}"

    content_type_value = str(content_type or "").split(";", 1)[0].strip().lower()
    guessed_ext = (mimetypes.guess_extension(content_type_value) or "").lower()
    if guessed_ext.startswith(".") and guessed_ext[1:] in allowed:
        if not stem:
            stem = secure_filename(Path(fallback).stem) or "url_video"
        return f"{stem}{guessed_ext}"

    fallback_stem = stem or secure_filename(Path(fallback).stem) or "url_video"
    return safe_video_filename(fallback, fallback_stem=fallback_stem, allowed_extensions=allowed)
