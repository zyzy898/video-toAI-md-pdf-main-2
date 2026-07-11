import asyncio
from pathlib import Path

import pytest

from services.output_templates import (
    CONTENT_SUMMARY,
    DEFAULT_OUTPUT_TEMPLATE,
    OPERATION_GUIDE,
    build_content_summary_fallback,
    is_content_summary_markdown,
    normalize_output_template,
)
from video_analyzer_agent import VideoAnalyzerAgent


SUMMARY_HEADINGS = (
    "# \u5185\u5bb9\u6458\u8981",
    "## \u6838\u5fc3\u6458\u8981",
    "## \u5173\u952e\u8981\u70b9",
    "## \u65f6\u95f4\u7ebf",
    "## \u7ed3\u8bba",
)


def _steps():
    return [
        {
            "step": 1,
            "time": "00:05",
            "title": "\u6253\u5f00\u8bbe\u7f6e",
            "description": "\u5728\u9876\u90e8\u83dc\u5355\u4e2d\u6253\u5f00\u8bbe\u7f6e\u9875\u9762\u3002",
        },
        {
            "step": 2,
            "time": "01:20",
            "title": "\u4fdd\u5b58\u914d\u7f6e",
            "description": "\u68c0\u67e5\u9009\u9879\u540e\u4fdd\u5b58\u65b0\u914d\u7f6e\u3002",
        },
    ]


class _ChatRecorder:
    def __init__(self, response: str):
        self.response = response
        self.messages = None

    async def __call__(self, messages, temperature=None):
        self.messages = messages
        return self.response


class _ToolText(str):
    def __new__(cls, value: str, completed_tool_types=()):
        result = super().__new__(cls, value)
        result.completed_tool_types = frozenset(completed_tool_types)
        return result


def _agent_with_chat(response: str):
    agent = object.__new__(VideoAnalyzerAgent)
    recorder = _ChatRecorder(response)
    agent._chat_completion_text = recorder
    return agent, recorder


@pytest.mark.parametrize("raw_value", [None, "", "   "])
def test_normalize_output_template_defaults_empty_values(raw_value):
    assert normalize_output_template(raw_value) == OPERATION_GUIDE
    assert DEFAULT_OUTPUT_TEMPLATE == OPERATION_GUIDE


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("operation_guide", OPERATION_GUIDE),
        (" content_summary ", CONTENT_SUMMARY),
    ],
)
def test_normalize_output_template_accepts_only_supported_values(raw_value, expected):
    assert normalize_output_template(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["summary_only", "guide", True, 1])
def test_normalize_output_template_rejects_invalid_values(raw_value):
    with pytest.raises(ValueError, match="output_template"):
        normalize_output_template(raw_value)


def test_content_summary_fallback_has_fixed_structure_without_steps_or_images():
    markdown = build_content_summary_fallback(_steps())

    heading_offsets = [markdown.index(heading) for heading in SUMMARY_HEADINGS]
    assert heading_offsets == sorted(heading_offsets)
    assert "## \u6b65\u9aa4" not in markdown
    assert "![" not in markdown
    assert "00:05" in markdown
    assert "\u6253\u5f00\u8bbe\u7f6e" in markdown
    assert "\u5728\u9876\u90e8\u83dc\u5355\u4e2d\u6253\u5f00\u8bbe\u7f6e\u9875\u9762\u3002" in markdown
    assert is_content_summary_markdown(markdown) is True


def test_content_summary_validator_rejects_missing_sections_and_step_layout():
    missing_conclusion = "\n\n".join(SUMMARY_HEADINGS[:-1])
    operation_guide = (
        "# \u64cd\u4f5c\u6307\u5357\n\n## \u6b65\u9aa4 1\uff1a\u6253\u5f00\u8bbe\u7f6e\n\n"
        "![\u622a\u56fe](images/step_01.jpg)"
    )

    assert is_content_summary_markdown(missing_conclusion) is False
    assert is_content_summary_markdown(operation_guide) is False


def test_generate_step_document_keeps_operation_guide_as_default(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    model_markdown = "# \u64cd\u4f5c\u6307\u5357\n\n## \u6b65\u9aa4 1\uff1a\u6253\u5f00\u8bbe\u7f6e\n"
    agent, recorder = _agent_with_chat(model_markdown)

    result = asyncio.run(agent.generate_step_document(_steps(), str(output_path)))

    assert result == str(output_path)
    assert output_path.read_text(encoding="utf-8") == model_markdown
    assert "## \u6b65\u9aa4 X" in recorder.messages[0]["content"]
    assert "\u622a\u56fe\u5bf9\u5e94\u5173\u7cfb" in recorder.messages[1]["content"]


def test_generate_content_summary_uses_summary_prompt_without_screenshot_list(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    model_markdown = "\n\n".join(SUMMARY_HEADINGS) + "\n"
    agent, recorder = _agent_with_chat(model_markdown)
    steps = _steps()
    steps[0]["evidence"] = {
        "screenshot": {"path": "images/private_capture.jpg"}
    }

    result = asyncio.run(
        agent.generate_step_document(
            steps,
            str(output_path),
            output_template=CONTENT_SUMMARY,
        )
    )

    assert result == str(output_path)
    assert output_path.read_text(encoding="utf-8") == model_markdown
    system_prompt = recorder.messages[0]["content"]
    user_prompt = recorder.messages[1]["content"]
    assert all(heading in system_prompt for heading in SUMMARY_HEADINGS)
    assert "## \u6b65\u9aa4 X" not in system_prompt
    assert "\u622a\u56fe\u5bf9\u5e94\u5173\u7cfb" not in user_prompt
    assert "![" not in user_prompt
    assert "private_capture.jpg" not in user_prompt
    assert '"evidence"' not in user_prompt


def test_web_search_summary_records_real_tool_usage_and_requests_reference_section(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    model_markdown = (
        "\n\n".join(SUMMARY_HEADINGS)
        + "\n\n### 参考资料\n- [官方文档](https://docs.example.com/guide)\n"
    )

    class ToolClient:
        provider = "ark"

        def __init__(self):
            self.messages = None

        def supports(self, _capability):
            return True

        async def responses_with_tools(self, *, messages, tools):
            self.messages = messages
            assert tools == [{"type": "web_search"}]
            return _ToolText(model_markdown, {"web_search_call"})

    agent = object.__new__(VideoAnalyzerAgent)
    agent.llm_client = ToolClient()

    asyncio.run(
        agent.generate_step_document(
            _steps(),
            str(output_path),
            web_search=True,
            output_template=CONTENT_SUMMARY,
        )
    )

    assert agent.last_document_web_search_used is True
    assert "### 参考资料" in agent.llm_client.messages[0]["content"]


def test_web_search_summary_does_not_record_usage_without_completed_tool_call(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    model_markdown = (
        "\n\n".join(SUMMARY_HEADINGS)
        + "\n\n### \u53c2\u8003\u8d44\u6599\n- [\u5b98\u65b9\u6587\u6863](https://docs.example.com/guide)\n"
    )

    class ToolClient:
        provider = "ark"

        def supports(self, _capability):
            return True

        async def responses_with_tools(self, *, messages, tools):
            return _ToolText(model_markdown)

    agent = object.__new__(VideoAnalyzerAgent)
    agent.llm_client = ToolClient()

    asyncio.run(
        agent.generate_step_document(
            _steps(),
            str(output_path),
            web_search=True,
            output_template=CONTENT_SUMMARY,
        )
    )

    assert agent.last_document_web_search_used is False


def test_content_summary_uses_matching_fallback_when_model_breaks_structure(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    agent, _ = _agent_with_chat(
        "# \u64cd\u4f5c\u6307\u5357\n\n## \u6b65\u9aa4 1\uff1a\u6a21\u578b\u8bef\u751f\u6210\n\n"
        "![\u622a\u56fe](images/step_01.jpg)\n"
    )

    asyncio.run(
        agent.generate_step_document(
            _steps(),
            str(output_path),
            respect_step_content=True,
            output_template=CONTENT_SUMMARY,
        )
    )

    markdown = output_path.read_text(encoding="utf-8")
    assert all(heading in markdown for heading in SUMMARY_HEADINGS)
    assert "## \u6b65\u9aa4" not in markdown
    assert "![" not in markdown
    assert "\u6253\u5f00\u8bbe\u7f6e" in markdown
    assert "\u5728\u9876\u90e8\u83dc\u5355\u4e2d\u6253\u5f00\u8bbe\u7f6e\u9875\u9762\u3002" in markdown


def test_content_summary_strict_mode_preserves_valid_aligned_model_output(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    model_markdown = """# \u5185\u5bb9\u6458\u8981

## \u6838\u5fc3\u6458\u8981
\u6253\u5f00\u8bbe\u7f6e\uff0c\u7136\u540e\u4fdd\u5b58\u914d\u7f6e\u3002

## \u5173\u952e\u8981\u70b9
- \u6253\u5f00\u8bbe\u7f6e\uff1a\u5728\u9876\u90e8\u83dc\u5355\u4e2d\u6253\u5f00\u8bbe\u7f6e\u9875\u9762\u3002
- \u4fdd\u5b58\u914d\u7f6e\uff1a\u68c0\u67e5\u9009\u9879\u540e\u4fdd\u5b58\u65b0\u914d\u7f6e\u3002

## \u65f6\u95f4\u7ebf
- 00:05 \u6253\u5f00\u8bbe\u7f6e
- 01:20 \u4fdd\u5b58\u914d\u7f6e

## \u7ed3\u8bba
\u5b8c\u6210\u8bbe\u7f6e\u540e\u8bb0\u5f97\u4fdd\u5b58\u3002
"""
    agent, _ = _agent_with_chat(model_markdown)

    asyncio.run(
        agent.generate_step_document(
            _steps(),
            str(output_path),
            respect_step_content=True,
            output_template=CONTENT_SUMMARY,
        )
    )

    assert output_path.read_text(encoding="utf-8") == model_markdown


def test_generate_step_document_rejects_invalid_template_before_writing(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    agent, recorder = _agent_with_chat("unused")

    with pytest.raises(ValueError, match="output_template"):
        asyncio.run(
            agent.generate_step_document(
                _steps(),
                str(output_path),
                output_template="summary_only",
            )
        )

    assert recorder.messages is None
    assert not Path(output_path).exists()


def test_operation_guide_prefers_safe_evidence_screenshot_in_prompt_and_fallback(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    steps = _steps()
    steps[0]["evidence"] = {
        "screenshot": {
            "path": "images/captured_at_5s.jpg",
            "time_seconds": 5,
        }
    }
    agent, recorder = _agent_with_chat("# \u4e0d\u5b8c\u6574\u7684\u6a21\u578b\u8f93\u51fa\n")

    asyncio.run(
        agent.generate_step_document(
            steps,
            str(output_path),
            respect_step_content=True,
        )
    )

    user_prompt = recorder.messages[1]["content"]
    markdown = output_path.read_text(encoding="utf-8")
    assert "![\u6b65\u9aa41\u622a\u56fe](images/captured_at_5s.jpg)" in user_prompt
    assert "![\u6b65\u9aa41\u622a\u56fe](images/captured_at_5s.jpg)" in markdown
    assert "images/step_01.jpg" not in user_prompt
    assert "images/step_01.jpg" not in markdown


def test_operation_guide_omits_images_without_explicit_screenshot_evidence(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    steps = _steps()[:1]
    agent, recorder = _agent_with_chat("# \u4e0d\u5b8c\u6574\u7684\u6a21\u578b\u8f93\u51fa\n")

    asyncio.run(
        agent.generate_step_document(
            steps,
            str(output_path),
            respect_step_content=True,
        )
    )

    user_prompt = recorder.messages[1]["content"]
    markdown = output_path.read_text(encoding="utf-8")
    assert "images/step_01.jpg" not in user_prompt
    assert "![" not in user_prompt
    assert "images/step_01.jpg" not in markdown
    assert "![" not in markdown
    assert agent._uses_provenance_screenshot_paths(
        "![\u622a\u56fe](images/step_01.jpg)", steps
    ) is False


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../private.jpg",
        "images/../private.jpg",
        "images/nested/private.jpg",
        "/images/private.jpg",
        "images/private).jpg",
        "outputs/private.jpg",
    ],
)
def test_operation_guide_rejects_unsafe_evidence_screenshot_paths(unsafe_path):
    agent = object.__new__(VideoAnalyzerAgent)
    steps = _steps()[:1]
    steps[0]["evidence"] = {"screenshot": {"path": unsafe_path}}

    markdown = agent._build_document_from_steps(steps)

    assert "![" not in markdown
    assert "images/step_01.jpg" not in markdown
    assert unsafe_path not in markdown


def test_operation_guide_fallback_escapes_user_supplied_image_markup():
    agent = object.__new__(VideoAnalyzerAgent)
    steps = _steps()[:1]
    steps[0]["title"] = "![remote](https://remote.example/title.png)"
    steps[0]["description"] = (
        '<img src="https://remote.example/description.png">\n'
        "![second](https://remote.example/second.png)"
    )

    markdown = agent._build_document_from_steps(steps)

    assert "![" not in markdown
    assert "<img" not in markdown.lower()
    assert "https://remote.example/title.png" in markdown
    assert "https://remote.example/description.png" in markdown
    assert agent._uses_provenance_screenshot_paths(markdown, steps) is True


@pytest.mark.parametrize(
    "invalid_markdown",
    [
        "```markdown\n" + "\n\n".join(SUMMARY_HEADINGS) + "\n```",
        "\n\n".join(SUMMARY_HEADINGS) + '\n\n<img src="images/step_01.jpg">',
        "\n\n".join(SUMMARY_HEADINGS)
        + '\n\n<object data="file:///C:/private/secret.png"></object>',
        "\n\n".join(SUMMARY_HEADINGS)
        + '\n\n<iframe src="https://attacker.example/pixel"></iframe>',
        "\n\n".join(SUMMARY_HEADINGS)
        + "\n\n<style>body{background-image:url(https://attacker.example/pixel)}</style>",
        "\n\n".join(SUMMARY_HEADINGS)
        + '\n\n<svg><image href="file:///C:/private/secret.png"></image></svg>',
        "\n\n".join(SUMMARY_HEADINGS)
        + "\n\n<object/data=https://attacker.example/pixel.png>",
        "\n\n".join(SUMMARY_HEADINGS)
        + "\n\n<iframe/src=https://attacker.example/pixel>",
        "\n\n".join(SUMMARY_HEADINGS) + "\n\n<svg/onload=alert(1)>",
        "\n\n".join(SUMMARY_HEADINGS) + "\n\n- \u6b65\u9aa4 1\uff1a\u6253\u5f00\u8bbe\u7f6e",
        "\n\n".join(SUMMARY_HEADINGS) + "\n\n- **\u6b65\u9aa4 1**\uff1a\u6253\u5f00\u8bbe\u7f6e",
        "\n\n".join(SUMMARY_HEADINGS) + "\n\n- \u7b2c\u4e00\u6b65\uff1a\u6253\u5f00\u8bbe\u7f6e",
        "\n\n".join(SUMMARY_HEADINGS) + "\n\n- \u622a\u56fe 1\uff1a[\u67e5\u770b](images/a.jpg)",
    ],
)
def test_content_summary_validator_rejects_disguised_step_or_image_layouts(
    invalid_markdown,
):
    assert is_content_summary_markdown(invalid_markdown) is False


@pytest.mark.parametrize(
    "dangerous_html",
    [
        '<object data="file:///C:/private/secret.png"></object>',
        '<iframe src="https://attacker.example/pixel"></iframe>',
        "<style>body{background-image:url(https://attacker.example/pixel)}</style>",
        '<svg><image href="file:///C:/private/secret.png"></image></svg>',
        "<object/data=https://attacker.example/pixel.png>",
        "<iframe/src=https://attacker.example/pixel>",
        "<svg/onload=alert(1)>",
    ],
)
def test_operation_guide_validator_rejects_raw_html_resources(dangerous_html):
    agent = object.__new__(VideoAnalyzerAgent)
    steps = _steps()[:1]
    markdown = f"# \u64cd\u4f5c\u6559\u7a0b\n\n{dangerous_html}\n"

    assert agent._uses_provenance_screenshot_paths(markdown, steps) is False


def test_content_summary_fallback_escapes_user_supplied_markdown_and_html():
    steps = _steps()[:1]
    steps[0]["title"] = "[\u6253\u5f00\u8bbe\u7f6e](https://example.com)"
    steps[0]["description"] = (
        "\u67e5\u770b ![\u4f2a\u9020\u622a\u56fe](images/injected.jpg) "
        '<img src="images/other.jpg">'
    )

    markdown = build_content_summary_fallback(steps)

    assert is_content_summary_markdown(markdown) is True
    assert "![\u4f2a\u9020\u622a\u56fe](images/injected.jpg)" not in markdown
    assert "<img" not in markdown.lower()


def test_content_summary_fallback_escapes_user_supplied_time_markdown():
    steps = _steps()[:1]
    steps[0]["time"] = "![\u4f2a\u9020\u622a\u56fe](images/injected.jpg)"

    markdown = build_content_summary_fallback(steps)

    assert is_content_summary_markdown(markdown) is True
    assert "![\u4f2a\u9020\u622a\u56fe](images/injected.jpg)" not in markdown


def test_content_summary_strict_mode_requires_the_complete_edited_description(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    description = "A" * 40 + "-required-tail"
    steps = [
        {
            "step": 1,
            "time": "00:05",
            "title": "Exact title",
            "description": description,
        }
    ]
    model_markdown = f"""# \u5185\u5bb9\u6458\u8981

## \u6838\u5fc3\u6458\u8981
Exact title

## \u5173\u952e\u8981\u70b9
- Exact title: {description[:32]}

## \u65f6\u95f4\u7ebf
- 00:05 Exact title

## \u7ed3\u8bba
Done.
"""
    agent, _ = _agent_with_chat(model_markdown)

    asyncio.run(
        agent.generate_step_document(
            steps,
            str(output_path),
            respect_step_content=True,
            output_template=CONTENT_SUMMARY,
        )
    )

    assert "required-tail" in output_path.read_text(encoding="utf-8")


def test_operation_guide_falls_back_when_model_ignores_evidence_screenshot(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    steps = _steps()[:1]
    steps[0]["evidence"] = {
        "screenshot": {"path": "images/captured_at_5s.jpg"}
    }
    model_markdown = """# \u64cd\u4f5c\u6307\u5357

## \u6b65\u9aa4 1\uff1a\u6253\u5f00\u8bbe\u7f6e

![\u6b65\u9aa41\u622a\u56fe](images/step_01.jpg)

\u5728\u9876\u90e8\u83dc\u5355\u4e2d\u6253\u5f00\u8bbe\u7f6e\u9875\u9762\u3002
"""
    agent, _ = _agent_with_chat(model_markdown)

    asyncio.run(agent.generate_step_document(steps, str(output_path)))

    markdown = output_path.read_text(encoding="utf-8")
    assert "images/captured_at_5s.jpg" in markdown
    assert "images/step_01.jpg" not in markdown


def test_operation_guide_strict_mode_requires_complete_edited_description(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    description = "B" * 40 + "-required-tail"
    steps = [
        {
            "step": 1,
            "time": "00:05",
            "title": "Exact title",
            "description": description,
        }
    ]
    model_markdown = f"""# \u64cd\u4f5c\u6307\u5357

## \u6b65\u9aa4 1\uff1aExact title

![\u6b65\u9aa41\u622a\u56fe](images/step_01.jpg)

{description[:32]}
"""
    agent, _ = _agent_with_chat(model_markdown)

    asyncio.run(
        agent.generate_step_document(
            steps,
            str(output_path),
            respect_step_content=True,
        )
    )

    assert "required-tail" in output_path.read_text(encoding="utf-8")


def test_operation_guide_ignores_hidden_evidence_link_and_rejects_extra_image(tmp_path):
    output_path = tmp_path / "operation_guide.md"
    steps = _steps()[:1]
    steps[0]["evidence"] = {
        "screenshot": {"path": "images/captured_at_5s.jpg"}
    }
    model_markdown = """# \u64cd\u4f5c\u6307\u5357

## \u6b65\u9aa4 1\uff1a\u6253\u5f00\u8bbe\u7f6e

<!-- ![\u9690\u85cf](images/captured_at_5s.jpg) -->
![\u9519\u8bef\u622a\u56fe](../../private.jpg)

\u5728\u9876\u90e8\u83dc\u5355\u4e2d\u6253\u5f00\u8bbe\u7f6e\u9875\u9762\u3002
"""
    agent, _ = _agent_with_chat(model_markdown)

    asyncio.run(agent.generate_step_document(steps, str(output_path)))

    markdown = output_path.read_text(encoding="utf-8")
    assert "images/captured_at_5s.jpg" in markdown
    assert "../../private.jpg" not in markdown
