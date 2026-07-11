import services.step_provenance as step_provenance


def extract_external_references_from_markdown(markdown, **kwargs):
    assert hasattr(step_provenance, "extract_external_references_from_markdown"), (
        "reference extraction is not implemented"
    )
    return step_provenance.extract_external_references_from_markdown(markdown, **kwargs)


def test_extract_references_uses_only_explicit_reference_section():
    markdown = """# 内容摘要

[正文中的链接](https://ignored.example.com/article)

## 参考资料
- [官方指南](https://docs.example.com/guide)
- [重复链接](https://docs.example.com/guide)
- [不安全链接](javascript:alert(1))
- ![截图](images/step_01.jpg)

## 结语
- [后续章节链接](https://ignored.example.com/after)
"""

    result = extract_external_references_from_markdown(
        markdown,
        source="ark_web_search",
    )

    assert len(result) == 1
    assert result[0]["title"] == "官方指南"
    assert result[0]["url"] == "https://docs.example.com/guide"
    assert result[0]["source"] == "ark_web_search"


def test_extract_references_returns_empty_without_reference_heading():
    assert (
        extract_external_references_from_markdown(
            "[模型自行给出的链接](https://example.com)",
            source="ark_web_search",
        )
        == []
    )


def test_extract_references_filters_source_and_applies_limit_after_validation():
    markdown = """## References
- [Bad](file:///private)
- [One](https://example.com/one)
- [Two](http://example.org/two)
"""

    result = extract_external_references_from_markdown(
        markdown,
        source="untrusted",
        limit=1,
    )

    assert [item["url"] for item in result] == ["https://example.com/one"]
    assert result[0]["source"] == "model_reference"


def test_extract_references_supports_crlf_and_balanced_url_parentheses():
    markdown = (
        "# Guide\r\n\r\n"
        "## References\r\n"
        "- [Function docs](https://example.com/functions/run_(value))\r\n"
    )

    result = extract_external_references_from_markdown(markdown)

    assert result[0]["url"] == "https://example.com/functions/run_(value)"


def test_extract_references_supports_optional_titles_and_trailing_punctuation():
    markdown = """## References
- [Official docs](https://example.com/guide "Official").
- [API](https://example.com/api).
"""

    result = extract_external_references_from_markdown(markdown)

    assert [item["url"] for item in result] == [
        "https://example.com/guide",
        "https://example.com/api",
    ]


def test_extract_references_ignores_fenced_fake_heading_before_real_section():
    markdown = """# Guide

```markdown
## References
- [Fake](https://fake.example.com/)
```

## References
- [Real](https://real.example.com/)
"""

    result = extract_external_references_from_markdown(markdown)

    assert [item["title"] for item in result] == ["Real"]
    assert [item["url"] for item in result] == ["https://real.example.com/"]


def test_extract_references_supports_indented_headings_and_stops_at_next_heading():
    markdown = """# Guide

  ## References
- [Real](https://real.example.com/)

  ## Next
- [Outside](https://outside.example.com/)
"""

    result = extract_external_references_from_markdown(markdown)

    assert [item["title"] for item in result] == ["Real"]


def test_extract_references_unescapes_destination_and_ignores_inline_code():
    markdown = r"""## References
- `[Fake](https://fake.example.com/)`
- [Escaped](https://example.com/foo\)bar)
"""

    result = extract_external_references_from_markdown(markdown)

    assert [item["title"] for item in result] == ["Escaped"]
    assert result[0]["url"] == "https://example.com/foo)bar"


def test_extract_references_supports_parenthesized_link_title():
    markdown = """## References
- [Docs](https://example.com/guide (Official docs))
"""

    result = extract_external_references_from_markdown(markdown)

    assert result[0]["url"] == "https://example.com/guide"
