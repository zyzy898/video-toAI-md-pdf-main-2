"""Tests for concurrent vision enhancement (VideoAnalyzerAgent.enhance_steps_with_vision).

These tests bypass __init__ via object.__new__ to avoid load_dotenv, API-key
validation, and the ffmpeg shim write. Only the attributes the method actually
touches are injected, and the single network dependency (_chat_completion_text)
is mocked.
"""

import asyncio
import base64
from pathlib import Path

import pytest

from video_analyzer_agent import VideoAnalyzerAgent


def _make_agent():
    """Construct an agent without running __init__."""
    return object.__new__(VideoAnalyzerAgent)


def _write_fake_screenshot(image_dir: Path, step_num: int):
    img_path = image_dir / f"step_{step_num:02d}.jpg"
    # Minimal non-empty bytes; the method only base64-encodes, never decodes.
    img_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return img_path


def _steps(n):
    return [
        {
            "step": i + 1,
            "time": f"00:{i:02d}",
            "title": f"原标题{i + 1}",
            "description": f"原描述{i + 1}",
            "confidence": 0.1,
        }
        for i in range(n)
    ]


class TestConcurrentEnhance:
    def test_index_alignment(self, tmp_path):
        """Each enhanced result must write back to its own steps[idx]."""
        agent = _make_agent()
        steps = _steps(3)
        for i in range(3):
            _write_fake_screenshot(tmp_path, i + 1)

        async def fake_chat(messages):
            # Echo the step number embedded in the user text so we can assert
            # the result lands on the correct index.
            user_text = messages[1]["content"][0]["text"]
            # "第N步" appears in the text
            num = int(user_text.split("第")[1].split("步")[0])
            return f'{{"title": "新标题{num}", "description": "新描述{num}"}}'

        agent._chat_completion_text = fake_chat

        result = asyncio.run(
            agent.enhance_steps_with_vision(steps, str(tmp_path), srt_path=None, max_calls=10)
        )

        for i in range(3):
            assert result[i]["title"] == f"新标题{i + 1}"
            assert result[i]["description"] == f"新描述{i + 1}"
            assert result[i]["enhanced"] is True

    def test_failure_is_isolated(self, tmp_path):
        """One step raising must not corrupt other steps; failed step keeps original."""
        agent = _make_agent()
        steps = _steps(3)
        for i in range(3):
            _write_fake_screenshot(tmp_path, i + 1)

        async def fake_chat(messages):
            user_text = messages[1]["content"][0]["text"]
            num = int(user_text.split("第")[1].split("步")[0])
            if num == 2:
                raise RuntimeError("simulated API failure")
            return f'{{"title": "新标题{num}", "description": "新描述{num}"}}'

        agent._chat_completion_text = fake_chat

        result = asyncio.run(
            agent.enhance_steps_with_vision(steps, str(tmp_path), srt_path=None, max_calls=10)
        )

        assert result[0]["title"] == "新标题1"
        assert result[0].get("enhanced") is True
        # Step 2 failed -> keeps original, not marked enhanced
        assert result[1]["title"] == "原标题2"
        assert result[1].get("enhanced") is not True
        assert result[2]["title"] == "新标题3"

    def test_missing_screenshot_skipped(self, tmp_path):
        """Steps whose screenshot file is absent are skipped, keep original values."""
        agent = _make_agent()
        steps = _steps(2)
        # Only create screenshot for step 1; step 2 has none.
        _write_fake_screenshot(tmp_path, 1)

        async def fake_chat(messages):
            return '{"title": "新标题", "description": "新描述"}'

        agent._chat_completion_text = fake_chat

        result = asyncio.run(
            agent.enhance_steps_with_vision(steps, str(tmp_path), srt_path=None, max_calls=10)
        )

        assert result[0]["title"] == "新标题"
        assert result[1]["title"] == "原标题2"
        assert result[1].get("enhanced") is not True

    def test_concurrency_env_clamped(self, tmp_path, monkeypatch):
        """VISION_MAX_CONCURRENCY is read and clamped to [1, 8]."""
        agent = _make_agent()
        steps = _steps(1)
        _write_fake_screenshot(tmp_path, 1)

        observed_concurrent = {"max": 0, "cur": 0}
        lock = asyncio.Lock()

        async def fake_chat(messages):
            async with lock:
                observed_concurrent["cur"] += 1
                observed_concurrent["max"] = max(
                    observed_concurrent["max"], observed_concurrent["cur"]
                )
            await asyncio.sleep(0.01)
            async with lock:
                observed_concurrent["cur"] -= 1
            return '{"title": "x", "description": "y"}'

        agent._chat_completion_text = fake_chat

        monkeypatch.setenv("VISION_MAX_CONCURRENCY", "999")
        result = asyncio.run(
            agent.enhance_steps_with_vision(steps, str(tmp_path), srt_path=None, max_calls=10)
        )
        assert result[0]["enhanced"] is True
