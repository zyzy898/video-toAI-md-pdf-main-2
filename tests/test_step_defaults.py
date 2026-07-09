from services.step_defaults import ensure_minimum_step_count


OVERVIEW_TITLE = "\u5185\u5bb9\u6982\u89c8"
KEY_TITLE = "\u5173\u952e\u4fe1\u606f\u63d0\u70bc"
NEXT_TITLE = "\u4e0b\u4e00\u6b65\u5efa\u8bae"


def test_ensure_minimum_step_count_returns_copy_when_enough_steps():
    steps = [{"step": 1, "title": "existing"}, {"step": 2, "title": "done"}]

    result = ensure_minimum_step_count(steps, min_steps=2, reason="ignored")

    assert result == steps
    assert result is not steps


def test_ensure_minimum_step_count_pads_default_steps_and_confidence():
    result = ensure_minimum_step_count([], min_steps=3)

    assert [item["step"] for item in result] == [1, 2, 3]
    assert [item["time"] for item in result] == ["00:00", "00:20", "00:40"]
    assert [item["title"] for item in result] == [OVERVIEW_TITLE, KEY_TITLE, NEXT_TITLE]
    assert [item["confidence"] for item in result] == [0.3, 0.27, 0.24]
    assert all(item["source"] == "fallback_padding" for item in result)


def test_ensure_minimum_step_count_appends_after_existing_steps_and_adds_reason_to_second_padding():
    steps = [{"step": 1, "time": "00:05", "title": "existing"}]

    result = ensure_minimum_step_count(steps, min_steps=3, reason="  low\n confidence  ")

    assert result[0] == steps[0]
    assert result[1]["step"] == 2
    assert result[1]["time"] == "00:20"
    assert result[1]["title"] == KEY_TITLE
    assert "low confidence" in result[1]["description"]
    assert result[2]["step"] == 3
    assert result[2]["title"] == NEXT_TITLE
    assert "low confidence" not in result[2]["description"]


def test_ensure_minimum_step_count_reuses_last_default_when_more_than_three_needed():
    result = ensure_minimum_step_count([], min_steps=5)

    assert [item["time"] for item in result] == ["00:00", "00:20", "00:40", "00:40", "00:40"]
    assert result[-1]["step"] == 5
    assert result[-1]["title"] == NEXT_TITLE
    assert result[-1]["confidence"] == 0.2
