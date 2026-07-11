from __future__ import annotations

import copy
import importlib
import math
import re

import pytest


ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _provenance_module():
    try:
        return importlib.import_module("services.step_provenance")
    except ModuleNotFoundError as exc:
        pytest.fail(f"step provenance module is not implemented: {exc}")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (12, 12.0),
        (12.75, 12.75),
        (-4, 0.0),
        ("12.5", 12.5),
        ("-12.5", 0.0),
        ("-00:05", 0.0),
        ("01:02", 62.0),
        ("01:02.5", 62.5),
        ("01:02,250", 62.25),
        ("01:02:03", 3723.0),
        ("01:02:03,500", 3723.5),
    ],
)
def test_parse_step_time_seconds_accepts_supported_formats(value, expected):
    parse_step_time_seconds = _provenance_module().parse_step_time_seconds

    assert parse_step_time_seconds(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [None, "", "not-a-time", "1:2:3:4", object(), math.nan, math.inf, -math.inf],
)
def test_parse_step_time_seconds_returns_zero_for_invalid_values(value):
    parse_step_time_seconds = _provenance_module().parse_step_time_seconds

    assert parse_step_time_seconds(value) == 0.0


def test_enrich_steps_returns_a_deep_copy_without_mutating_any_input():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    steps = [
        {
            "step": 1,
            "time": "00:05",
            "title": "Open settings",
            "legacy": {"tags": ["keep-me"]},
            "evidence": {
                "legacy_note": {"status": "keep"},
                "external_reference_ids": ["ref_one"],
            },
        }
    ]
    raw_subtitles = [
        {
            "index": 1,
            "start_time": "00:00:05,000",
            "end_time": "00:00:06,000",
            "start_seconds": 5,
            "end_seconds": 6,
            "text": "raw line",
        }
    ]
    analyzed_subtitles = [
        {
            "index": 1,
            "start_time": "00:00:05,000",
            "end_time": "00:00:06,000",
            "start_seconds": 5,
            "end_seconds": 6,
            "text": "analyzed line",
        }
    ]
    originals = copy.deepcopy((steps, raw_subtitles, analyzed_subtitles))

    result = enrich_steps_with_evidence(
        steps,
        raw_subtitles=raw_subtitles,
        analyzed_subtitles=analyzed_subtitles,
    )

    assert (steps, raw_subtitles, analyzed_subtitles) == originals
    assert result is not steps
    assert result[0] is not steps[0]
    assert result[0]["legacy"] is not steps[0]["legacy"]
    assert result[0]["evidence"]["legacy_note"] == {"status": "keep"}
    result[0]["legacy"]["tags"].append("result-only")
    result[0]["evidence"]["legacy_note"]["status"] = "changed"
    assert steps[0]["legacy"] == {"tags": ["keep-me"]}
    assert steps[0]["evidence"]["legacy_note"] == {"status": "keep"}


def test_enrich_steps_preserves_valid_ids_and_generates_stable_unique_ids():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    steps = [
        {"step_id": "keep_ME-1", "time": "00:00", "title": "A"},
        {"step_id": "bad id", "time": "00:10", "title": "B"},
        {"step_id": "keep_ME-1", "time": "00:20", "title": "C"},
        {"step_id": "x" * 81, "time": "00:30", "title": "D"},
        {"time": "00:40", "title": "same"},
        {"time": "00:40", "title": "same"},
    ]

    first = enrich_steps_with_evidence(steps)
    second = enrich_steps_with_evidence(steps)
    first_ids = [item["step_id"] for item in first]

    assert first[0]["step_id"] == "keep_ME-1"
    assert first[2]["step_id"] != "keep_ME-1"
    assert first_ids == [item["step_id"] for item in second]
    assert len(first_ids) == len(set(first_ids))
    assert all(ID_PATTERN.fullmatch(step_id) for step_id in first_ids)


def test_generated_step_id_ignores_unrelated_or_non_json_metadata():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    first = enrich_steps_with_evidence(
        [{"step": 1, "time": "00:05", "title": "A", "legacy": {"beta", "alpha"}}]
    )
    second = enrich_steps_with_evidence(
        [{"step": 1, "time": "00:05", "title": "A", "legacy": {"changed"}}]
    )

    assert first[0]["step_id"] == second[0]["step_id"]


def test_enrich_steps_binds_raw_and_analyzed_subtitles_by_index_and_time_window():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    steps = [
        {"step": 1, "time": "00:05", "title": "First"},
        {"step": 2, "time": "00:15", "title": "Second"},
    ]
    raw_subtitles = [
        {"index": 4, "text": "raw four"},
        {"index": 2, "text": "raw two"},
        {"index": 3, "text": "raw three"},
        {"index": 1, "text": "raw one"},
    ]
    analyzed_subtitles = [
        {
            "index": 1,
            "start_time": "00:00:04,500",
            "end_time": "00:00:05,500",
            "start_seconds": 4.5,
            "end_seconds": 5.5,
            "text": "analyzed one",
        },
        {
            "index": 2,
            "start_time": "00:00:08,000",
            "end_time": "00:00:09,000",
            "start_seconds": 8,
            "end_seconds": 9,
            "text": "analyzed two",
        },
        {
            "index": 3,
            "start_time": "00:00:14,500",
            "end_time": "00:00:15,500",
            "start_seconds": 14.5,
            "end_seconds": 15.5,
            "text": "analyzed three",
        },
        {
            "index": 4,
            "start_time": "00:00:16,000",
            "end_time": "00:00:17,000",
            "start_seconds": 16,
            "end_seconds": 17,
            "text": "analyzed four",
        },
    ]

    result = enrich_steps_with_evidence(
        steps,
        raw_subtitles=raw_subtitles,
        analyzed_subtitles=analyzed_subtitles,
    )

    assert [item["time_seconds"] for item in result] == [5.0, 15.0]
    assert [item["index"] for item in result[0]["evidence"]["subtitles"]] == [1, 2, 3]
    assert [item["index"] for item in result[1]["evidence"]["subtitles"]] == [3, 4]
    bound = result[0]["evidence"]["subtitles"][1]
    assert bound == {
        "index": 2,
        "start_time": "00:00:08,000",
        "end_time": "00:00:09,000",
        "start_seconds": 8.0,
        "end_seconds": 9.0,
        "raw_text": "raw two",
        "analyzed_text": "analyzed two",
    }


def test_enrich_steps_uses_the_next_strictly_greater_time_and_limits_six_lines():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    steps = [
        {"step": 1, "time": "00:10"},
        {"step": 2, "time": "00:10"},
        {"step": 3, "time": "00:20"},
    ]
    analyzed_subtitles = [
        {
            "index": index,
            "start_time": f"00:00:{10 + index:02d},000",
            "end_time": f"00:00:{10 + index:02d},500",
            "start_seconds": 10 + index,
            "end_seconds": 10.5 + index,
            "text": f"line {index}",
        }
        for index in range(1, 9)
    ]
    analyzed_subtitles.extend(
        [
            "not-a-dict",
            {"index": 20, "start_seconds": 12, "end_seconds": 13, "text": ""},
            {"index": 21, "start_seconds": "bad", "end_seconds": 13, "text": "bad time"},
        ]
    )

    result = enrich_steps_with_evidence(steps, analyzed_subtitles=analyzed_subtitles)

    first_indices = [item["index"] for item in result[0]["evidence"]["subtitles"]]
    second_indices = [item["index"] for item in result[1]["evidence"]["subtitles"]]
    assert first_indices == [1, 2, 3, 4, 5, 6]
    assert second_indices == first_indices
    assert result[2]["evidence"]["subtitles"] == []


def test_enrich_steps_never_presents_analyzed_text_as_missing_raw_text():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    analyzed_subtitles = [
        {
            "index": 50,
            "start_time": "00:00:01,000",
            "end_time": "00:00:02,000",
            "start_seconds": 1,
            "end_seconds": 2,
            "text": "analyzed only",
        }
    ]

    result = enrich_steps_with_evidence(
        [{"step": 1, "time": "00:00"}],
        raw_subtitles=[{"index": 1, "text": "unrelated raw"}],
        analyzed_subtitles=analyzed_subtitles,
    )

    subtitle = result[0]["evidence"]["subtitles"][0]
    assert subtitle["raw_text"] == ""
    assert subtitle["analyzed_text"] == "analyzed only"


def test_enrich_steps_never_binds_raw_text_when_analyzed_index_is_missing():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence

    result = enrich_steps_with_evidence(
        [{"step": 1, "time": "00:00"}],
        raw_subtitles=[
            {
                "index": 1,
                "start_seconds": 1,
                "end_seconds": 2,
                "text": "raw one",
            }
        ],
        analyzed_subtitles=[
            {
                "start_seconds": 1,
                "end_seconds": 2,
                "text": "analyzed without index",
            }
        ],
    )

    analyzed = next(
        item
        for item in result[0]["evidence"]["subtitles"]
        if item["analyzed_text"]
    )
    assert analyzed["raw_text"] == ""


def test_enrich_steps_keeps_raw_only_rows_when_analysis_is_partial():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    raw_subtitles = [
        {"index": 1, "start_seconds": 1, "end_seconds": 2, "text": "raw one"},
        {"index": 2, "start_seconds": 3, "end_seconds": 4, "text": "raw two"},
    ]
    analyzed_subtitles = [
        {
            "index": 1,
            "start_seconds": 1,
            "end_seconds": 2,
            "text": "fixed one",
        }
    ]

    result = enrich_steps_with_evidence(
        [{"step": 1, "time": "00:00"}],
        raw_subtitles=raw_subtitles,
        analyzed_subtitles=analyzed_subtitles,
    )

    assert [item["index"] for item in result[0]["evidence"]["subtitles"]] == [1, 2]
    assert result[0]["evidence"]["subtitles"][1]["raw_text"] == "raw two"
    assert result[0]["evidence"]["subtitles"][1]["analyzed_text"] == ""


def test_enrich_steps_uses_raw_timing_when_matching_analyzed_row_has_no_time():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence

    result = enrich_steps_with_evidence(
        [{"step": 1, "time": "00:00"}],
        raw_subtitles=[
            {
                "index": 7,
                "start_time": "00:00:02,000",
                "end_time": "00:00:03,000",
                "start_seconds": 2,
                "end_seconds": 3,
                "text": "raw seven",
            }
        ],
        analyzed_subtitles=[{"index": 7, "text": "fixed seven"}],
    )

    assert result[0]["evidence"]["subtitles"][0]["raw_text"] == "raw seven"
    assert result[0]["evidence"]["subtitles"][0]["analyzed_text"] == "fixed seven"
    assert result[0]["evidence"]["subtitles"][0]["start_seconds"] == 2.0


def test_enrich_steps_falls_back_to_legacy_seconds_when_display_time_is_invalid():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence

    result = enrich_steps_with_evidence(
        [{"step": 1, "time": "invalid", "time_seconds": 12.0}]
    )

    assert result[0]["time_seconds"] == 12.0


def test_enrich_steps_adds_only_real_screenshot_files(tmp_path):
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    image_dir = tmp_path / "generated-images"
    image_dir.mkdir()
    (image_dir / "step_01.jpg").write_bytes(b"jpeg")
    (image_dir / "step_02.jpg").mkdir()
    (image_dir / "step_04.jpg").write_bytes(b"")
    steps = [
        {"step": 1, "time": "00:01"},
        {
            "step": 2,
            "time": "00:02",
            "evidence": {"screenshot": {"path": "stale.jpg"}},
        },
        {"step": 3, "time": "00:03"},
        {"step": 4, "time": "00:04"},
    ]

    result = enrich_steps_with_evidence(steps, image_dir=image_dir)

    assert result[0]["evidence"]["screenshot"] == {
        "path": "images/step_01.jpg",
        "captured_at_seconds": 1.0,
    }
    assert "screenshot" not in result[1]["evidence"]
    assert "screenshot" not in result[2]["evidence"]
    assert "screenshot" not in result[3]["evidence"]


def test_enrich_steps_preserves_valid_external_reference_ids_or_defaults_empty():
    enrich_steps_with_evidence = _provenance_module().enrich_steps_with_evidence
    steps = [
        {
            "time": "00:00",
            "evidence": {"external_reference_ids": ["ref_1", "ref-two"]},
        },
        {"time": "00:10", "evidence": {"external_reference_ids": "ref_3"}},
        {
            "time": "00:20",
            "evidence": {"external_reference_ids": ["ref_4", "bad id"]},
        },
        {"time": "00:30"},
    ]

    result = enrich_steps_with_evidence(steps)

    assert result[0]["evidence"]["external_reference_ids"] == ["ref_1", "ref-two"]
    assert result[1]["evidence"]["external_reference_ids"] == []
    assert result[2]["evidence"]["external_reference_ids"] == []
    assert result[3]["evidence"]["external_reference_ids"] == []


def test_normalize_external_references_filters_unsafe_urls_and_deduplicates():
    normalize_external_references = _provenance_module().normalize_external_references
    raw_refs = [
        {
            "id": "kept_ID-1",
            "title": "Primary source",
            "url": "https://docs.example.com/guide",
            "source": "ark_web_search",
        },
        {"url": "https://docs.example.com/guide", "title": "duplicate"},
        {"url": "javascript:alert(1)"},
        {"url": "file:///tmp/reference"},
        {"url": "data:text/plain,unsafe"},
        {"url": "https://user:secret@example.com/private"},
        {"url": "https:///missing-host"},
        {"url": "https://example.com\\unsafe"},
        {"url": "https://example.com/\\evil.example"},
        "not-a-dict",
        {
            "title": "   ",
            "url": "http://example.org/reference",
            "source": "untrusted_source",
        },
    ]

    result = normalize_external_references(raw_refs)

    assert len(result) == 2
    assert result[0]["id"] != "kept_ID-1"
    assert result[0]["title"] == "Primary source"
    assert result[0]["url"] == "https://docs.example.com/guide"
    assert result[0]["source"] == "model_reference"
    assert result[1]["title"] == "example.org"
    assert result[1]["url"] == "http://example.org/reference"
    assert result[1]["source"] == "model_reference"
    assert ID_PATTERN.fullmatch(result[1]["id"])


def test_normalize_external_references_generates_stable_unique_ids():
    normalize_external_references = _provenance_module().normalize_external_references
    raw_refs = [
        {"id": "shared", "url": "https://example.com/a"},
        {"id": "shared", "url": "https://example.com/b"},
        {"id": "bad id", "url": "https://example.com/c"},
        {"url": "https://example.com/d"},
    ]

    first = normalize_external_references(raw_refs)
    second = normalize_external_references(raw_refs)
    ids = [item["id"] for item in first]

    assert all(item["id"] != "shared" for item in first)
    assert ids == [item["id"] for item in second]
    assert len(ids) == len(set(ids))
    assert all(ID_PATTERN.fullmatch(ref_id) for ref_id in ids)


def test_normalize_external_references_uses_canonical_url_identity_and_trusted_source():
    normalize_external_references = _provenance_module().normalize_external_references
    raw_refs = [
        {"url": "HTTP://EXAMPLE.COM:80/a", "source": "model_reference"},
        {"url": "http://example.com/a"},
        {"url": "https://example.com"},
        {"url": "https://EXAMPLE.com/"},
    ]

    first = normalize_external_references(raw_refs, source="ark_web_search")
    second = normalize_external_references(list(reversed(raw_refs)), source="ark_web_search")

    assert [item["url"] for item in first] == [
        "http://example.com/a",
        "https://example.com/",
    ]
    assert {item["id"] for item in first} == {item["id"] for item in second}
    assert {item["source"] for item in first} == {"ark_web_search"}


def test_normalize_external_references_applies_limit_after_filtering():
    normalize_external_references = _provenance_module().normalize_external_references
    raw_refs = [
        {"url": "javascript:alert(1)"},
        {"url": "https://example.com/one"},
        {"url": "https://example.com/two"},
        {"url": "https://example.com/three"},
    ]

    assert [
        item["url"] for item in normalize_external_references(raw_refs, limit=2)
    ] == ["https://example.com/one", "https://example.com/two"]
    assert normalize_external_references(raw_refs, limit=0) == []
