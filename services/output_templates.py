from __future__ import annotations

import html
import re
from typing import Any, Iterable, Literal, Mapping, TypeAlias, cast


OPERATION_GUIDE = "operation_guide"
CONTENT_SUMMARY = "content_summary"
DEFAULT_OUTPUT_TEMPLATE = OPERATION_GUIDE

OutputTemplate: TypeAlias = Literal["operation_guide", "content_summary"]

_VALID_OUTPUT_TEMPLATES = frozenset({OPERATION_GUIDE, CONTENT_SUMMARY})
_SUMMARY_HEADINGS = (
    (1, "\u5185\u5bb9\u6458\u8981"),
    (2, "\u6838\u5fc3\u6458\u8981"),
    (2, "\u5173\u952e\u8981\u70b9"),
    (2, "\u65f6\u95f4\u7ebf"),
    (2, "\u7ed3\u8bba"),
)
_MARKDOWN_HEADING_RE = re.compile(
    r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$",
    re.MULTILINE,
)
_FENCED_CODE_RE = re.compile(
    r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_MARKDOWN_IMAGE_RE = re.compile(r"(?<!\\)!\[")
_MARKDOWN_IMAGE_LINK_RE = re.compile(
    r"(?<!\\)!\[[^\]]*\]\(\s*([^\s)]+)\s*\)"
)
_HTML_IMAGE_RE = re.compile(r"<\s*img\b", re.IGNORECASE)
_RAW_HTML_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z]", re.IGNORECASE)
_STEP_HEADING_RE = re.compile(
    r"^#{2,6}[ \t]+(?:\u6b65\u9aa4\s*\d+|step\s*\d+)",
    re.IGNORECASE | re.MULTILINE,
)
_STEP_LIST_RE = re.compile(
    r"^[ \t]*(?:[-+*]|\d+[.)])[ \t]+(?:\*{1,2}|_{1,2})?"
    r"(?:"
    r"\u6b65\u9aa4[ \t]*\d+"
    r"|step[ \t]*\d+"
    r"|\u7b2c(?:\d+|[\u96f6\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]+)\u6b65"
    r"|\u622a\u56fe(?:[ \t]*\d+)?"
    r")"
    r"(?:\*{1,2}|_{1,2})?(?=$|[\s:\uff1a.\-])",
    re.IGNORECASE | re.MULTILINE,
)
_MARKDOWN_INLINE_ESCAPE_RE = re.compile(r"([`*_\[\]()!])")


def normalize_output_template(value: Any = None) -> OutputTemplate:
    """Return a supported template name, defaulting only empty input."""
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        return cast(OutputTemplate, DEFAULT_OUTPUT_TEMPLATE)
    if normalized not in _VALID_OUTPUT_TEMPLATES:
        allowed = ", ".join(sorted(_VALID_OUTPUT_TEMPLATES))
        raise ValueError(f"output_template must be one of: {allowed}")
    return cast(OutputTemplate, normalized)


def _single_line(value: Any, default: str = "") -> str:
    text = "" if value is None else str(value)
    compact = " ".join(text.split())
    return compact or default


def _escape_markdown_inline(value: str) -> str:
    escaped = html.escape(value, quote=False).replace("\\", "\\\\")
    return _MARKDOWN_INLINE_ESCAPE_RE.sub(r"\\\1", escaped)


def escape_markdown_text(value: Any) -> str:
    """Render untrusted text literally in Markdown and generated HTML."""

    return _escape_markdown_inline("" if value is None else str(value))


def _visible_markdown_source(markdown_content: Any) -> str:
    content = "" if markdown_content is None else str(markdown_content)
    content = _HTML_COMMENT_RE.sub("", content)
    return _FENCED_CODE_RE.sub("", content)


def _normalize_comparison_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip().lower())


def _summary_items(steps: Iterable[Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, Mapping):
            continue
        title = _escape_markdown_inline(
            _single_line(raw_step.get("title"), f"\u8981\u70b9 {index}")
        )
        items.append(
            {
                "time": _escape_markdown_inline(
                    _single_line(raw_step.get("time"), "00:00")
                ),
                "title": title,
                "description": _escape_markdown_inline(
                    _single_line(
                        raw_step.get("description"),
                        "\uff08\u672a\u586b\u5199\u5185\u5bb9\u8bf4\u660e\uff09",
                    )
                ),
            }
        )
    return items


def build_content_summary_fallback(steps: Iterable[Any]) -> str:
    """Build a deterministic content summary without step or image sections."""
    items = _summary_items(steps)
    if items:
        topic_preview = "\u3001".join(item["title"] for item in items[:3])
        core_summary = (
            f"\u672c\u89c6\u9891\u56f4\u7ed5{topic_preview}\u5c55\u5f00\uff0c"
            f"\u5171\u63d0\u70bc {len(items)} \u4e2a\u5173\u952e\u5185\u5bb9\u8282\u70b9\u3002"
        )
        conclusion = (
            "\u4ee5\u4e0a\u8981\u70b9\u6982\u62ec\u4e86\u89c6\u9891\u7684\u4e3b\u8981\u5185\u5bb9\uff0c"
            "\u53ef\u7ed3\u5408\u65f6\u95f4\u7ebf\u56de\u770b\u539f\u89c6\u9891\u3002"
        )
    else:
        core_summary = "\u6682\u65e0\u53ef\u7528\u7684\u5185\u5bb9\u6458\u8981\u3002"
        conclusion = (
            "\u5f53\u524d\u7f3a\u5c11\u53ef\u603b\u7ed3\u7684\u5185\u5bb9\uff0c"
            "\u5efa\u8bae\u8865\u5145\u5b57\u5e55\u6216\u91cd\u65b0\u5206\u6790\u3002"
        )

    lines = [
        "# \u5185\u5bb9\u6458\u8981",
        "",
        "## \u6838\u5fc3\u6458\u8981",
        core_summary,
        "",
        "## \u5173\u952e\u8981\u70b9",
    ]
    if items:
        for item in items:
            lines.append(f"- **{item['title']}**\uff1a{item['description']}")
    else:
        lines.append("- \u6682\u65e0\u5173\u952e\u8981\u70b9\u3002")

    lines.extend(["", "## \u65f6\u95f4\u7ebf"])
    if items:
        for item in items:
            lines.append(f"- {item['time']}\uff1a{item['title']}")
    else:
        lines.append("- 00:00\uff1a\u6682\u65e0\u65f6\u95f4\u7ebf\u4fe1\u606f\u3002")

    lines.extend(["", "## \u7ed3\u8bba", conclusion, ""])
    return "\n".join(lines)


def is_content_summary_markdown(markdown_content: Any) -> bool:
    """Check the exact top-level summary structure and reject image/step layouts."""
    content = _visible_markdown_source(markdown_content)
    if (
        not content.strip()
        or _MARKDOWN_IMAGE_RE.search(content)
        or _HTML_IMAGE_RE.search(content)
        or _RAW_HTML_TAG_RE.search(content)
        or _STEP_HEADING_RE.search(content)
        or _STEP_LIST_RE.search(content)
    ):
        return False

    headings = [
        (len(match.group(1)), match.group(2).strip())
        for match in _MARKDOWN_HEADING_RE.finditer(content)
        if len(match.group(1)) <= 2
    ]
    return headings == list(_SUMMARY_HEADINGS)


def is_content_summary_aligned_with_steps(
    markdown_content: Any,
    steps: Iterable[Any],
) -> bool:
    """Check full edited titles and descriptions against rendered summary content."""
    if not is_content_summary_markdown(markdown_content):
        return False

    normalized_doc = _normalize_comparison_text(
        _visible_markdown_source(markdown_content)
    )
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        for field in ("title", "description"):
            anchor = _normalize_comparison_text(step.get(field))
            if anchor and anchor not in normalized_doc:
                return False
    return True


def is_operation_guide_aligned_with_steps(
    markdown_content: Any,
    steps: Iterable[Any],
) -> bool:
    """Check complete edited content against visible operation-guide Markdown."""
    normalized_doc = _normalize_comparison_text(
        _visible_markdown_source(markdown_content)
    )
    if not normalized_doc:
        return False

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, Mapping):
            continue
        for field in ("title", "description"):
            anchor = _normalize_comparison_text(step.get(field))
            if anchor and anchor not in normalized_doc:
                return False

        step_no = step.get("step", index)
        zh_anchor = _normalize_comparison_text(f"\u6b65\u9aa4{step_no}")
        en_anchor = _normalize_comparison_text(f"step{step_no}")
        if zh_anchor not in normalized_doc and en_anchor not in normalized_doc:
            return False
    return True


def uses_only_expected_image_paths(
    markdown_content: Any,
    *,
    allowed_paths: Iterable[str],
    required_paths: Iterable[str],
) -> bool:
    """Validate visible Markdown images against explicit local path sets."""
    content = _visible_markdown_source(markdown_content)
    if _HTML_IMAGE_RE.search(content) or _RAW_HTML_TAG_RE.search(content):
        return False

    matches = list(_MARKDOWN_IMAGE_LINK_RE.finditer(content))
    content_without_links = _MARKDOWN_IMAGE_LINK_RE.sub("", content)
    if _MARKDOWN_IMAGE_RE.search(content_without_links):
        return False

    actual = {match.group(1) for match in matches}
    allowed = {str(path) for path in allowed_paths}
    required = {str(path) for path in required_paths}
    return required.issubset(actual) and actual.issubset(allowed)


__all__ = [
    "CONTENT_SUMMARY",
    "DEFAULT_OUTPUT_TEMPLATE",
    "OPERATION_GUIDE",
    "OutputTemplate",
    "build_content_summary_fallback",
    "escape_markdown_text",
    "is_content_summary_aligned_with_steps",
    "is_content_summary_markdown",
    "is_operation_guide_aligned_with_steps",
    "normalize_output_template",
    "uses_only_expected_image_paths",
]
