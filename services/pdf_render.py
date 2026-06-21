"""High-fidelity Markdown -> PDF rendering via headless Chromium (Playwright).

The legacy path (FPDF + regex HTML stripping) loses tables, nested lists, code
blocks and link styling. This module renders the Markdown to a styled HTML page
and prints it to PDF with Chromium, which preserves full CSS layout and CJK
fonts on Windows without the native GTK/Pango stack WeasyPrint requires.

Design choices:
  * Pure-sync Playwright API, executed in a worker thread by the caller so it
    never collides with an existing asyncio loop (batch mode uses threads).
  * The HTML file is written next to the Markdown so relative image paths
    (``images/step_01.jpg``) resolve against a ``file://`` base URL.
  * Everything is best-effort: callers check the boolean return and fall back
    to the existing FPDF renderer when Chromium is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


def is_available() -> bool:
    """True when Playwright (and an installed Chromium) can be imported."""
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return True


def _markdown_to_html_body(md_content: str) -> str:
    """Render Markdown to an HTML fragment with the useful extensions enabled."""
    import markdown

    return markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br", "toc"],
    )


# Print-oriented stylesheet. @page handles margins/size so Chromium's own
# header/footer can stay off. Fonts list common CJK families across platforms.
_PAGE_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
               "WenQuanYi Micro Hei", "SimSun", sans-serif;
  font-size: 11pt; line-height: 1.7; color: #2c3e50;
  margin: 0; padding: 0;
}
h1 { font-size: 20pt; color: #1a1a1a; border-bottom: 2px solid #3498db;
     padding-bottom: 8px; margin: 0 0 16px; }
h2 { font-size: 15pt; color: #2c3e50; margin: 22px 0 10px;
     padding-left: 10px; border-left: 4px solid #3498db;
     page-break-after: avoid; }
h3 { font-size: 12.5pt; color: #34495e; margin: 14px 0 6px;
     page-break-after: avoid; }
p { margin: 6px 0; }
ul, ol { margin: 6px 0 6px 4px; padding-left: 22px; }
li { margin: 3px 0; }
strong { color: #1a1a1a; }
code { background: #f4f6f8; padding: 1px 5px; border-radius: 3px;
       font-family: "Consolas", "Courier New", monospace; font-size: 10pt; }
pre { background: #f4f6f8; border: 1px solid #e1e4e8; border-radius: 6px;
      padding: 12px; overflow-x: auto; line-height: 1.45;
      page-break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0;
        page-break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 7px 10px; text-align: left;
         vertical-align: top; }
th { background: #f0f3f6; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
a { color: #2563eb; text-decoration: none; }
blockquote { margin: 10px 0; padding: 6px 14px; color: #57606a;
             border-left: 4px solid #d0d7de; background: #f6f8fa; }
img { max-width: 88%; max-height: 150mm; display: block;
      margin: 10px auto; border: 1px solid #e1e4e8; border-radius: 4px; }
/* Keep "## 步骤 X" sections from splitting title away from their figure. */
h2 + p, h2 + p + p { page-break-inside: avoid; }
hr { border: none; border-top: 1px solid #e1e4e8; margin: 18px 0; }
"""


def _build_html_document(md_content: str) -> str:
    """Wrap the rendered Markdown body in a full, print-styled HTML document."""
    body = _markdown_to_html_body(md_content)
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\">"
        f"<style>{_PAGE_CSS}</style>"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )


def render_markdown_to_pdf(md_path: str, pdf_path: str) -> bool:
    """Render ``md_path`` to ``pdf_path`` via headless Chromium.

    Returns True on success, False on any failure (so the caller can fall back
    to FPDF). Never raises for an expected/operational problem.

    The HTML is written into the Markdown's own directory under a temp name so
    relative image references resolve against ``file://`` and are embedded by
    Chromium at print time.
    """
    if not is_available():
        return False

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        logging.warning("[pdf_render] Playwright 不可用，回退 FPDF: %s", exc)
        return False

    md_file = Path(md_path)
    try:
        md_content = md_file.read_text(encoding="utf-8")
    except OSError as exc:
        logging.warning("[pdf_render] 读取 Markdown 失败: %s", exc)
        return False

    html_doc = _build_html_document(md_content)
    base_dir = md_file.parent
    html_tmp = base_dir / f".{md_file.stem}.render.html"

    try:
        html_tmp.write_text(html_doc, encoding="utf-8")
    except OSError as exc:
        logging.warning("[pdf_render] 写入临时 HTML 失败: %s", exc)
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                # file:// base URL lets relative images/CSS resolve locally.
                page.goto(html_tmp.resolve().as_uri(), wait_until="networkidle")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                )
            finally:
                browser.close()
    except Exception as exc:
        logging.warning("[pdf_render] Chromium 渲染失败，回退 FPDF: %s", str(exc)[:200])
        return False
    finally:
        try:
            if html_tmp.exists():
                html_tmp.unlink()
        except OSError:
            pass

    ok = Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 0
    if not ok:
        logging.warning("[pdf_render] 输出 PDF 为空，回退 FPDF")
    return ok


__all__ = ["is_available", "render_markdown_to_pdf"]
