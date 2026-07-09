import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
STEPS_PATH = REPO_ROOT / "steps.json"
VIDEO_PATH = REPO_ROOT / "test_1.mp4"


def test_screenshot_generation_with_local_fixtures():
    """Run screenshot generation only when the large local fixtures are present."""
    missing_fixtures = [
        fixture.name
        for fixture in (STEPS_PATH, VIDEO_PATH)
        if not fixture.exists()
    ]
    if missing_fixtures:
        pytest.skip(
            "requires local screenshot fixtures: "
            + ", ".join(missing_fixtures)
        )

    from video_analyzer_agent import VideoAnalyzerAgent

    steps = json.loads(STEPS_PATH.read_text(encoding="utf-8"))
    assert isinstance(steps, list)

    test_steps = steps[:3]
    assert test_steps, "steps.json must contain at least one step"

    agent = VideoAnalyzerAgent()
    screenshot_paths = agent.generate_screenshots_from_steps(str(VIDEO_PATH), test_steps)

    assert len(screenshot_paths) == len(test_steps)
    for screenshot_path in screenshot_paths:
        assert Path(screenshot_path).exists()
