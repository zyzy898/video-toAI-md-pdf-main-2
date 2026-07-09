from services.subtitle_steps import (
    extract_action_phrase_from_subtitle,
    pick_timeline_points_from_subtitles,
)


def test_extract_action_phrase_from_subtitle_finds_known_verb_and_compacts_object():
    text = "\u8bf7\u5148\u70b9\u51fb \u786e\u8ba4\u6309\u94ae\uff0c\u7136\u540e\u8fdb\u5165\u4e0b\u4e00\u6b65"

    assert extract_action_phrase_from_subtitle(text) == (
        "\u70b9\u51fb",
        "\u786e\u8ba4\u6309\u94ae",
    )


def test_extract_action_phrase_from_subtitle_removes_leading_filler_words():
    text = "\u9700\u8981\u6253\u5f00\u4e00\u4e0b \u8bbe\u7f6e \u9875\u9762"

    assert extract_action_phrase_from_subtitle(text) == (
        "\u6253\u5f00",
        "\u8bbe\u7f6e \u9875\u9762",
    )


def test_extract_action_phrase_from_subtitle_returns_empty_for_non_action_text():
    assert extract_action_phrase_from_subtitle("plain subtitle") == ("", "")
    assert extract_action_phrase_from_subtitle(None) == ("", "")


def test_pick_timeline_points_from_subtitles_ignores_empty_items_and_normalizes_times():
    subtitles = [
        {"start_seconds": 0, "text": "zero"},
        {"start_seconds": "bad", "text": ""},
        "ignored",
        {"start_seconds": "12.5", "text": " first\npoint "},
        {"start_seconds": -3, "text": "negative"},
    ]

    assert pick_timeline_points_from_subtitles(subtitles, minimum=3, max_steps=5) == [
        {"time": "00:00", "text": "zero", "start_seconds": 0.0, "raw": subtitles[0]},
        {"time": "00:12", "text": "first point", "start_seconds": 12.5, "raw": subtitles[3]},
        {"time": "00:00", "text": "negative", "start_seconds": 0.0, "raw": subtitles[4]},
    ]


def test_pick_timeline_points_from_subtitles_samples_evenly_with_max_steps_cap():
    subtitles = [
        {"start_seconds": index * 10, "text": f"item {index}"}
        for index in range(6)
    ]

    timeline = pick_timeline_points_from_subtitles(subtitles, minimum=3, max_steps=5)

    assert [item["text"] for item in timeline] == [
        "item 0",
        "item 1",
        "item 3",
        "item 4",
        "item 5",
    ]
    assert [item["time"] for item in timeline] == ["00:00", "00:10", "00:30", "00:40", "00:50"]
