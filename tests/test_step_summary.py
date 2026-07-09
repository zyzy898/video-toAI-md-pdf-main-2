from services.step_summary import build_key_points_from_steps, extract_timeline_from_steps


WAITING_SEGMENT = "\u5f85\u786e\u8ba4\u7247\u6bb5"
WAITING_POINT = "00:00\uff1a\u5f85\u786e\u8ba4\u8981\u70b9"


def test_extract_timeline_from_steps_compacts_titles_and_fills_defaults():
    steps = [
        {"time": " 00:05 ", "title": "  open\n menu  "},
        "ignored",
        {"time": "", "title": "   "},
    ]

    assert extract_timeline_from_steps(steps, limit=5, min_steps=3) == [
        {"time": "00:05", "text": "open menu"},
        {"time": "00:20", "text": WAITING_SEGMENT},
        {"time": "00:40", "text": WAITING_SEGMENT},
    ]


def test_extract_timeline_from_steps_uses_default_time_and_caps_real_items():
    steps = [
        {"time": "", "title": "First"},
        {"time": "00:10", "title": "Second"},
        {"time": "00:20", "title": "Third"},
    ]

    assert extract_timeline_from_steps(steps, limit=2, min_steps=3) == [
        {"time": "00:00", "text": "First"},
        {"time": "00:10", "text": "Second"},
        {"time": "00:40", "text": WAITING_SEGMENT},
    ]


def test_build_key_points_from_steps_prefers_title_then_description_and_fills_defaults():
    steps = [
        {"time": "00:03", "title": "  Click\n button  ", "description": "ignored"},
        {"time": "", "title": "", "description": " fallback\n description "},
        "ignored",
    ]

    assert build_key_points_from_steps(steps, limit=5, min_points=3) == [
        "00:03\uff1aClick button",
        "00:00\uff1afallback description",
        WAITING_POINT,
    ]


def test_build_key_points_from_steps_caps_before_adding_defaults():
    steps = [
        {"time": "00:01", "title": "One"},
        {"time": "00:02", "title": "Two"},
        {"time": "00:03", "title": "Three"},
    ]

    assert build_key_points_from_steps(steps, limit=2, min_points=3) == [
        "00:01\uff1aOne",
        "00:02\uff1aTwo",
    ]
