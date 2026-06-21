"""Tests for the Chromium-based PDF renderer's pure helpers (services.pdf_render).

The actual Chromium print path needs a browser, so it is not exercised here;
these tests cover the deterministic HTML/CSS assembly and graceful degradation.
"""

from services import pdf_render


def test_is_available_returns_bool():
    assert isinstance(pdf_render.is_available(), bool)


def test_html_document_is_well_formed():
    html = pdf_render._build_html_document("# 标题\n\n正文内容")
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html
    assert "标题" in html
    assert html.rstrip().endswith("</html>")


def test_markdown_table_rendered_as_html_table():
    md = "| A | B |\n| - | - |\n| 1 | 2 |"
    body = pdf_render._markdown_to_html_body(md)
    assert "<table>" in body
    assert "<td>" in body


def test_markdown_fenced_code_preserved():
    md = "```python\nprint('hi')\n```"
    body = pdf_render._markdown_to_html_body(md)
    assert "<code" in body or "<pre" in body


def test_css_targets_cjk_and_print_layout():
    assert "@page" in pdf_render._PAGE_CSS
    assert "YaHei" in pdf_render._PAGE_CSS or "CJK" in pdf_render._PAGE_CSS


def test_render_returns_false_for_missing_markdown(tmp_path):
    missing = tmp_path / "nope.md"
    out = tmp_path / "out.pdf"
    # Missing source must degrade to False (caller falls back to FPDF), not raise.
    assert pdf_render.render_markdown_to_pdf(str(missing), str(out)) is False
