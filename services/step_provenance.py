"""Pure helpers for attaching source evidence to analyzed video steps."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import string
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_PLAIN_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_TIMESTAMP_RE = re.compile(
    r"^(?P<first>[+-]?\d+):(?P<second>\d+(?:[.,]\d+)?)"
    r"(?::(?P<third>\d+(?:[.,]\d+)?))?$"
)
_ALLOWED_REFERENCE_SOURCES = {"ark_web_search", "model_reference"}
_MAX_SUBTITLE_EVIDENCE = 6
_REFERENCE_HEADING_RE = re.compile(
    r"^[ \t]{0,3}(?P<marks>#{1,6})[ \t]+(?:参考资料|外部引用|references|sources)[ \t]*#*[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)
_MARKDOWN_FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})(?P<tail>.*)$")
_MARKDOWN_HEADING_RE = re.compile(r"^[ \t]{0,3}(?P<marks>#{1,6})[ \t]+")


def _parse_time_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    if not isinstance(value, str):
        try:
            parsed_number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed_number if math.isfinite(parsed_number) else None

    text = value.strip()
    if not text:
        return None

    if _PLAIN_NUMBER_RE.fullmatch(text):
        try:
            parsed_number = float(text.replace(",", "."))
        except ValueError:
            return None
        return parsed_number if math.isfinite(parsed_number) else None

    match = _TIMESTAMP_RE.fullmatch(text)
    if match is None:
        return None

    first_text = match.group("first")
    is_negative = first_text.startswith("-")
    first = abs(int(first_text))
    second_text = match.group("second")
    third_text = match.group("third")
    try:
        if third_text is None:
            seconds = float(second_text.replace(",", "."))
            if seconds >= 60:
                return None
            total = float(first * 60) + seconds
            return -total if is_negative else total

        if not second_text.isdigit():
            return None
        minutes = int(second_text)
        seconds = float(third_text.replace(",", "."))
        if minutes >= 60 or seconds >= 60:
            return None
        total = float(first * 3600 + minutes * 60) + seconds
        return -total if is_negative else total
    except (TypeError, ValueError, OverflowError):
        return None


def parse_step_time_seconds(value: Any) -> float:
    """Parse a numeric, MM:SS, or HH:MM:SS step time into nonnegative seconds."""
    parsed = _parse_time_value(value)
    if parsed is None or not math.isfinite(parsed):
        return 0.0
    return max(0.0, float(parsed))


def _is_valid_id(value: Any) -> bool:
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


def _claim_generated_id(base: str, unavailable: set[str]) -> str:
    candidate = base[:80]
    counter = 2
    while candidate in unavailable:
        suffix = f"-{counter}"
        candidate = f"{base[: 80 - len(suffix)]}{suffix}"
        counter += 1
    unavailable.add(candidate)
    return candidate


def _step_id_seed(step: dict[str, Any], position: int) -> str:
    stable_fields = {
        "position": position,
        "step": _step_number(step, position),
        "time_seconds": _step_time_seconds(step),
        "title": step.get("title") if isinstance(step.get("title"), str) else "",
        "description": (
            step.get("description") if isinstance(step.get("description"), str) else ""
        ),
    }
    serialized = json.dumps(
        stable_fields,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8", errors="replace")).hexdigest()[:16]


def _preserved_id_positions(items: list[dict[str, Any]]) -> tuple[dict[int, str], set[str]]:
    positions: dict[int, str] = {}
    reserved: set[str] = set()
    for index, item in enumerate(items):
        item_id = item.get("step_id")
        if _is_valid_id(item_id) and item_id not in reserved:
            positions[index] = item_id
            reserved.add(item_id)
    return positions, reserved


def _step_time_seconds(step: dict[str, Any]) -> float:
    raw_time = step.get("time")
    has_time = raw_time is not None and (
        not isinstance(raw_time, str) or bool(raw_time.strip())
    )
    if has_time:
        parsed = _parse_time_value(raw_time)
        if parsed is not None:
            return max(0.0, float(parsed))
    return parse_step_time_seconds(step.get("time_seconds"))


def _as_items(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes, bytearray, dict)):
        return []
    try:
        return list(value)
    except (TypeError, ValueError):
        return []


def _subtitle_index(value: Any, fallback: int) -> int | str:
    explicit = _explicit_subtitle_index(value)
    return fallback if explicit is None else explicit


def _explicit_subtitle_index(value: Any) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer() and value > 0:
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() and int(text) > 0:
            return int(text)
        if text and len(text) <= 80:
            return text
    return None


def _subtitle_text(item: dict[str, Any], *, analyzed: bool) -> str:
    fields = ("analyzed_text", "text") if analyzed else ("raw_text", "text")
    for field in fields:
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _subtitle_seconds(
    item: dict[str, Any],
    seconds_field: str,
    timestamp_field: str,
) -> float | None:
    for field in (seconds_field, timestamp_field):
        if field not in item:
            continue
        value = item.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        parsed = _parse_time_value(value)
        if parsed is not None and parsed >= 0:
            return float(parsed)
    return None


def _raw_subtitle_map(raw_items: list[Any]) -> dict[int | str, str]:
    raw_by_index: dict[int | str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = _subtitle_text(item, analyzed=False)
        if not text:
            continue
        index = _explicit_subtitle_index(item.get("index"))
        if index is None:
            continue
        raw_by_index.setdefault(index, text)
    return raw_by_index


def _overlaps_window(
    subtitle_start: float,
    subtitle_end: float,
    window_start: float,
    window_end: float,
) -> bool:
    if subtitle_end > subtitle_start:
        return subtitle_start < window_end and subtitle_end > window_start
    return window_start <= subtitle_start < window_end


def _subtitle_evidence_for_window(
    *,
    raw_items: list[Any],
    analyzed_items: list[Any],
    raw_by_index: dict[int | str, str],
    window_start: float,
    window_end: float,
) -> list[dict[str, Any]]:
    raw_items_by_index: dict[int | str, dict[str, Any]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        raw_index = _explicit_subtitle_index(raw_item.get("index"))
        if raw_index is not None:
            raw_items_by_index.setdefault(raw_index, raw_item)

    candidates_by_index: dict[int | str, dict[str, Any]] = {}
    unindexed_candidates: list[dict[str, Any]] = []
    sources = [(item, True, position) for position, item in enumerate(analyzed_items, start=1)]
    sources.extend(
        (item, False, position) for position, item in enumerate(raw_items, start=1)
    )
    for order, (item, is_analyzed, position) in enumerate(sources):
        if not isinstance(item, dict):
            continue

        primary_text = _subtitle_text(item, analyzed=is_analyzed)
        if not primary_text:
            continue

        explicit_index = _explicit_subtitle_index(item.get("index"))
        raw_timing_item = (
            raw_items_by_index.get(explicit_index)
            if is_analyzed and explicit_index is not None
            else None
        )
        start_seconds = _subtitle_seconds(item, "start_seconds", "start_time")
        end_seconds = _subtitle_seconds(item, "end_seconds", "end_time")
        if start_seconds is None and raw_timing_item is not None:
            start_seconds = _subtitle_seconds(
                raw_timing_item, "start_seconds", "start_time"
            )
        if end_seconds is None and raw_timing_item is not None:
            end_seconds = _subtitle_seconds(raw_timing_item, "end_seconds", "end_time")
        if start_seconds is None:
            continue
        if end_seconds is None:
            end_seconds = start_seconds
        if end_seconds < start_seconds:
            continue
        if not _overlaps_window(start_seconds, end_seconds, window_start, window_end):
            continue

        index = explicit_index if explicit_index is not None else position
        raw_text = raw_by_index.get(explicit_index, "") if explicit_index is not None else ""
        if not is_analyzed:
            raw_text = primary_text
        start_time = str(item.get("start_time", "") or "").strip()
        end_time = str(item.get("end_time", "") or "").strip()
        if raw_timing_item is not None:
            start_time = start_time or str(
                raw_timing_item.get("start_time", "") or ""
            ).strip()
            end_time = end_time or str(
                raw_timing_item.get("end_time", "") or ""
            ).strip()
        candidate = {
            "index": index,
            "start_time": start_time,
            "end_time": end_time,
            "start_seconds": float(start_seconds),
            "end_seconds": float(end_seconds),
            "raw_text": raw_text,
            "analyzed_text": primary_text if is_analyzed else "",
            "_is_analyzed": is_analyzed,
            "_order": order,
        }
        if explicit_index is None:
            unindexed_candidates.append(candidate)
            continue
        existing = candidates_by_index.get(explicit_index)
        if existing is None or (is_analyzed and not existing["_is_analyzed"]):
            candidates_by_index[explicit_index] = candidate

    evidence = [*candidates_by_index.values(), *unindexed_candidates]
    evidence.sort(
        key=lambda item: (
            item["start_seconds"],
            item["end_seconds"],
            0 if item["_is_analyzed"] else 1,
            item["_order"],
        )
    )
    for item in evidence:
        item.pop("_is_analyzed", None)
        item.pop("_order", None)
    return evidence[:_MAX_SUBTITLE_EVIDENCE]


def _external_reference_ids(existing_evidence: dict[str, Any]) -> list[str]:
    raw_ids = existing_evidence.get("external_reference_ids")
    if not isinstance(raw_ids, list) or not all(_is_valid_id(item) for item in raw_ids):
        return []
    return list(raw_ids)


def _step_number(step: dict[str, Any], fallback: int) -> int:
    raw_number = step.get("step", fallback)
    if isinstance(raw_number, bool):
        return fallback
    try:
        number = int(raw_number)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return number if number > 0 else fallback


def _screenshot_path(image_dir: Any, step_number: int) -> Path | None:
    if image_dir is None:
        return None
    try:
        candidate = Path(image_dir) / f"step_{step_number:02d}.jpg"
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size <= 0
        ):
            return None
    except (OSError, TypeError, ValueError):
        return None
    return candidate


def enrich_steps_with_evidence(
    steps: Iterable[Any],
    *,
    raw_subtitles: Any = None,
    analyzed_subtitles: Any = None,
    image_dir: Any = None,
) -> list[dict[str, Any]]:
    """Return copied steps enriched with stable IDs and source evidence."""
    step_items = [item for item in _as_items(steps) if isinstance(item, dict)]
    copied_steps = [copy.deepcopy(item) for item in step_items]
    preserved_ids, unavailable_ids = _preserved_id_positions(copied_steps)

    times = [_step_time_seconds(item) for item in copied_steps]
    raw_items = _as_items(raw_subtitles)
    analyzed_items = _as_items(analyzed_subtitles)
    raw_by_index = _raw_subtitle_map(raw_items)

    enriched: list[dict[str, Any]] = []
    for index, step in enumerate(copied_steps):
        if index in preserved_ids:
            step_id = preserved_ids[index]
        else:
            digest = _step_id_seed(step, index + 1)
            step_id = _claim_generated_id(f"step-{digest}", unavailable_ids)

        current_time = times[index]
        next_time = next(
            (later for later in times[index + 1 :] if later > current_time),
            current_time + 30.0,
        )
        existing_evidence = step.get("evidence")
        if not isinstance(existing_evidence, dict):
            existing_evidence = {}
        evidence = copy.deepcopy(existing_evidence)
        evidence["subtitles"] = _subtitle_evidence_for_window(
            raw_items=raw_items,
            analyzed_items=analyzed_items,
            raw_by_index=raw_by_index,
            window_start=current_time,
            window_end=next_time,
        )
        evidence["external_reference_ids"] = _external_reference_ids(existing_evidence)
        evidence["anchor_time_seconds"] = current_time
        evidence.pop("screenshot", None)

        step_number = _step_number(step, index + 1)
        if _screenshot_path(image_dir, step_number) is not None:
            evidence["screenshot"] = {
                "path": f"images/step_{step_number:02d}.jpg",
                "captured_at_seconds": current_time,
            }

        step["step_id"] = step_id
        step["time_seconds"] = current_time
        step["evidence"] = evidence
        enriched.append(step)
    return enriched


def _validated_reference_url(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    if (
        not url
        or "\\" in url
        or any(character.isspace() or ord(character) < 32 for character in url)
    ):
        return None

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        return None
    if "\\" in parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    normalized_netloc = hostname.lower()
    if ":" in normalized_netloc and not normalized_netloc.startswith("["):
        normalized_netloc = f"[{normalized_netloc}]"
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        normalized_netloc = f"{normalized_netloc}:{port}"
    normalized_url = urlunsplit(
        (
            scheme,
            normalized_netloc,
            parsed.path or "/",
            parsed.query,
            parsed.fragment,
        )
    )
    return normalized_url, hostname, normalized_url


def _reference_limit(value: Any) -> int:
    if isinstance(value, bool):
        return 20
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 20


def normalize_external_references(
    raw_refs: Any,
    limit: int = 20,
    *,
    source: str = "model_reference",
) -> list[dict[str, Any]]:
    """Filter and normalize model/web references into a stable safe schema."""
    max_items = _reference_limit(limit)
    if max_items <= 0:
        return []
    trusted_source = source if source in _ALLOWED_REFERENCE_SOURCES else "model_reference"

    candidates: list[tuple[dict[str, Any], str, str]] = []
    seen_urls: set[str] = set()
    for item in _as_items(raw_refs):
        if not isinstance(item, dict):
            continue
        validated = _validated_reference_url(item.get("url"))
        if validated is None:
            continue
        url, hostname, dedupe_key = validated
        if dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)
        candidates.append((item, url, hostname))
        if len(candidates) >= max_items:
            break

    unavailable_ids: set[str] = set()

    normalized: list[dict[str, Any]] = []
    for item, url, hostname in candidates:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        reference_id = _claim_generated_id(f"ref-{digest}", unavailable_ids)

        title_value = item.get("title")
        title = title_value.strip() if isinstance(title_value, str) else ""
        normalized.append(
            {
                "id": reference_id,
                "title": title or hostname,
                "url": url,
                "source": trusted_source,
            }
        )
    return normalized


def reconcile_edited_step_evidence(
    steps: Iterable[Any],
    *,
    original_steps: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Preserve evidence across edits, invalidating time-bound data after time changes."""
    copied_steps = [
        copy.deepcopy(item) for item in _as_items(steps) if isinstance(item, dict)
    ]
    preserved_ids, unavailable_ids = _preserved_id_positions(copied_steps)
    use_original_steps = original_steps is not None
    original_by_id: dict[str, dict[str, Any]] = {}
    if use_original_steps:
        for original in _as_items(original_steps):
            if not isinstance(original, dict):
                continue
            original_id = original.get("step_id")
            if _is_valid_id(original_id):
                original_by_id.setdefault(original_id, original)

    reconciled: list[dict[str, Any]] = []
    for index, step in enumerate(copied_steps):
        current_time = _step_time_seconds(step)
        original_id = step.get("step_id")
        trusted_step = (
            original_by_id.get(original_id)
            if use_original_steps and _is_valid_id(original_id)
            else (None if use_original_steps else step)
        )
        prior_time = _parse_time_value(
            trusted_step.get("time_seconds") if isinstance(trusted_step, dict) else None
        )
        prior_time_is_valid = prior_time is not None and prior_time >= 0
        existing_evidence = (
            trusted_step.get("evidence") if isinstance(trusted_step, dict) else None
        )
        evidence = copy.deepcopy(existing_evidence) if isinstance(existing_evidence, dict) else {}
        evidence_anchor = _parse_time_value(evidence.get("anchor_time_seconds"))
        screenshot = evidence.get("screenshot")
        screenshot_anchor = _parse_time_value(
            screenshot.get("captured_at_seconds") if isinstance(screenshot, dict) else None
        )
        has_time_bound_evidence = bool(evidence.get("subtitles")) or isinstance(
            screenshot, dict
        )
        if evidence_anchor is not None and evidence_anchor >= 0:
            trusted_anchor = evidence_anchor
        elif screenshot_anchor is not None and screenshot_anchor >= 0:
            trusted_anchor = screenshot_anchor
        elif use_original_steps or not has_time_bound_evidence:
            trusted_anchor = prior_time
        else:
            trusted_anchor = None
        time_changed = (
            not prior_time_is_valid
            or trusted_anchor is None
            or not math.isclose(
                float(trusted_anchor),
                current_time,
                rel_tol=0.0,
                abs_tol=0.001,
            )
        )

        evidence["external_reference_ids"] = _external_reference_ids(evidence)
        if time_changed:
            evidence.pop("subtitles", None)
            evidence.pop("screenshot", None)
        evidence["anchor_time_seconds"] = current_time

        if index in preserved_ids:
            step_id = preserved_ids[index]
        else:
            digest = _step_id_seed(step, index + 1)
            step_id = _claim_generated_id(f"step-{digest}", unavailable_ids)
        step["step_id"] = step_id
        step["time_seconds"] = current_time
        step["evidence"] = evidence
        reconciled.append(step)
    return reconciled


def extract_external_references_from_markdown(
    markdown_content: Any,
    *,
    source: str = "model_reference",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Extract links only from an explicit Markdown reference section."""
    content = "" if markdown_content is None else str(markdown_content)
    visible_lines = _visible_markdown_lines(content)
    reference_start = -1
    reference_level = 0
    for index, line in enumerate(visible_lines):
        heading = _REFERENCE_HEADING_RE.match(line)
        if heading is not None:
            reference_start = index + 1
            reference_level = len(heading.group("marks"))
            break
    if reference_start < 0:
        return []

    section_lines: list[str] = []
    for line in visible_lines[reference_start:]:
        heading = _MARKDOWN_HEADING_RE.match(line)
        if heading is not None and len(heading.group("marks")) <= reference_level:
            break
        section_lines.append(line)

    raw_references = [
        {"title": title, "url": url}
        for line in section_lines
        for title, url in _markdown_links_from_line(line)
    ]
    return normalize_external_references(
        raw_references,
        limit=limit,
        source=source,
    )


def _visible_markdown_lines(content: str) -> list[str]:
    """Return non-fenced Markdown lines so code examples cannot become evidence."""
    visible: list[str] = []
    fence_character = ""
    fence_length = 0
    for line in content.splitlines():
        fence = _MARKDOWN_FENCE_RE.match(line)
        if fence is not None:
            marker = fence.group("marker")
            if not fence_character:
                fence_character = marker[0]
                fence_length = len(marker)
                continue
            if (
                marker[0] == fence_character
                and len(marker) >= fence_length
                and not fence.group("tail").strip()
            ):
                fence_character = ""
                fence_length = 0
                continue
        if not fence_character:
            visible.append(line)
    return visible


def _markdown_links_from_line(line: str) -> list[tuple[str, str]]:
    """Parse ordinary inline links while respecting nested destination parentheses."""
    line = _strip_inline_code_spans(line)
    links: list[tuple[str, str]] = []
    cursor = 0
    while cursor < len(line):
        open_label = line.find("[", cursor)
        if open_label < 0:
            break
        if (
            (open_label > 0 and line[open_label - 1] in {"!", "\\"})
            or open_label + 1 >= len(line)
        ):
            cursor = open_label + 1
            continue

        close_label = _find_unescaped_character(line, "]", open_label + 1)
        if close_label < 0:
            break
        open_destination = close_label + 1
        while open_destination < len(line) and line[open_destination] in " \t":
            open_destination += 1
        if open_destination >= len(line) or line[open_destination] != "(":
            cursor = close_label + 1
            continue

        parsed = _parse_markdown_link_destination(line, open_destination)
        if parsed is None:
            cursor = open_destination + 1
            continue
        destination, link_end = parsed
        title = line[open_label + 1 : close_label].replace("\\]", "]").strip()
        if title and destination:
            links.append((title, destination))
        cursor = link_end
    return links


def _find_unescaped_character(text: str, character: str, start: int) -> int:
    cursor = start
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == character:
            return cursor
        cursor += 1
    return -1


def _strip_inline_code_spans(line: str) -> str:
    chars = list(line)
    cursor = 0
    while cursor < len(line):
        open_tick = line.find("`", cursor)
        if open_tick < 0:
            break
        run_end = open_tick
        while run_end < len(line) and line[run_end] == "`":
            run_end += 1
        marker = line[open_tick:run_end]
        close_tick = line.find(marker, run_end)
        if close_tick < 0:
            break
        close_end = close_tick + len(marker)
        chars[open_tick:close_end] = " " * (close_end - open_tick)
        cursor = close_end
    return "".join(chars)


def _unescape_markdown_destination(destination: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(destination):
        if (
            destination[cursor] == "\\"
            and cursor + 1 < len(destination)
            and destination[cursor + 1] in string.punctuation
        ):
            output.append(destination[cursor + 1])
            cursor += 2
            continue
        output.append(destination[cursor])
        cursor += 1
    return "".join(output)


def _parse_markdown_link_destination(
    line: str,
    open_parenthesis: int,
) -> tuple[str, int] | None:
    cursor = open_parenthesis + 1
    while cursor < len(line) and line[cursor] in " \t":
        cursor += 1
    if cursor >= len(line):
        return None

    if line[cursor] == "<":
        close_angle = _find_unescaped_character(line, ">", cursor + 1)
        if close_angle < 0:
            return None
        destination = line[cursor + 1 : close_angle]
        cursor = close_angle + 1
    else:
        destination_start = cursor
        nested_parentheses = 0
        while cursor < len(line):
            character = line[cursor]
            if character == "\\":
                cursor += 2
                continue
            if character == "(":
                nested_parentheses += 1
            elif character == ")":
                if nested_parentheses == 0:
                    return (
                        _unescape_markdown_destination(
                            line[destination_start:cursor]
                        ),
                        cursor + 1,
                    )
                nested_parentheses -= 1
            elif character in " \t" and nested_parentheses == 0:
                break
            cursor += 1
        destination = line[destination_start:cursor]

    while cursor < len(line) and line[cursor] in " \t":
        cursor += 1
    if cursor < len(line) and line[cursor] in {'"', "'"}:
        quote = line[cursor]
        close_quote = _find_unescaped_character(line, quote, cursor + 1)
        if close_quote < 0:
            return None
        cursor = close_quote + 1
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
    elif cursor < len(line) and line[cursor] == "(":
        title_depth = 0
        while cursor < len(line):
            character = line[cursor]
            if character == "\\":
                cursor += 2
                continue
            if character == "(":
                title_depth += 1
            elif character == ")":
                title_depth -= 1
                if title_depth == 0:
                    cursor += 1
                    break
            cursor += 1
        if title_depth != 0:
            return None
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
    if cursor >= len(line) or line[cursor] != ")":
        return None
    return _unescape_markdown_destination(destination), cursor + 1
