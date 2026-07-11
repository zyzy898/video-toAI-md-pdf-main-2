from __future__ import annotations

import copy

import services.step_provenance as step_provenance


def reconcile_edited_step_evidence(steps):
    assert hasattr(step_provenance, "reconcile_edited_step_evidence"), (
        "edited-step evidence reconciliation is not implemented"
    )
    return step_provenance.reconcile_edited_step_evidence(steps)


def _step(step_id: str, step: int, time: str, seconds: float, image: str):
    return {
        "step_id": step_id,
        "step": step,
        "time": time,
        "time_seconds": seconds,
        "title": f"Step {step}",
        "evidence": {
            "subtitles": [{"index": step, "raw_text": "raw", "analyzed_text": "fixed"}],
            "screenshot": {"path": image, "captured_at_seconds": seconds},
            "external_reference_ids": ["ref_one"],
            "legacy_note": {"keep": True},
        },
    }


def test_reconcile_edit_preserves_evidence_by_stable_id_when_only_reordered():
    original = [
        _step("step_a", 1, "00:05", 5.0, "images/step_01.jpg"),
        _step("step_b", 2, "00:20", 20.0, "images/step_02.jpg"),
    ]
    edited = copy.deepcopy([original[1], original[0]])
    edited[0]["step"] = 1
    edited[0]["title"] = "Renamed second step"
    edited[1]["step"] = 2
    snapshot = copy.deepcopy(edited)

    result = reconcile_edited_step_evidence(edited)

    assert edited == snapshot
    assert [item["step_id"] for item in result] == ["step_b", "step_a"]
    assert result[0]["evidence"]["screenshot"]["path"] == "images/step_02.jpg"
    assert result[1]["evidence"]["subtitles"][0]["index"] == 1


def test_reconcile_edit_invalidates_time_bound_evidence_when_time_changes():
    edited = _step("step_a", 1, "00:08", 5.0, "images/step_01.jpg")

    result = reconcile_edited_step_evidence([edited])

    assert result[0]["time_seconds"] == 8.0
    assert "subtitles" not in result[0]["evidence"]
    assert "screenshot" not in result[0]["evidence"]
    assert result[0]["evidence"]["external_reference_ids"] == ["ref_one"]
    assert result[0]["evidence"]["legacy_note"] == {"keep": True}


def test_reconcile_edit_treats_missing_or_invalid_prior_time_as_stale():
    missing_time = _step("step_a", 1, "00:05", 5.0, "images/step_01.jpg")
    missing_time.pop("time_seconds")
    invalid_time = _step("step_b", 2, "00:10", 10.0, "images/step_02.jpg")
    invalid_time["time_seconds"] = "not-a-time"

    result = reconcile_edited_step_evidence([missing_time, invalid_time])

    assert all("subtitles" not in item["evidence"] for item in result)
    assert all("screenshot" not in item["evidence"] for item in result)
    assert [item["time_seconds"] for item in result] == [5.0, 10.0]


def test_reconcile_edit_uses_persisted_step_as_trusted_evidence_source():
    persisted = _step("step_a", 1, "00:05", 5.0, "images/step_01.jpg")
    submitted = copy.deepcopy(persisted)
    submitted["time"] = "00:08"
    submitted["time_seconds"] = 8.0
    submitted["evidence"]["screenshot"]["captured_at_seconds"] = 8.0

    result = step_provenance.reconcile_edited_step_evidence(
        [submitted],
        original_steps=[persisted],
    )

    assert result[0]["time_seconds"] == 8.0
    assert "subtitles" not in result[0]["evidence"]
    assert "screenshot" not in result[0]["evidence"]


def test_reconcile_edit_invalidates_legacy_subtitles_without_independent_anchor():
    submitted = {
        "step_id": "step_a",
        "step": 1,
        "time": "00:08",
        "time_seconds": 8.0,
        "evidence": {
            "subtitles": [{"index": 1, "raw_text": "old", "analyzed_text": "old"}],
            "external_reference_ids": [],
        },
    }

    result = step_provenance.reconcile_edited_step_evidence([submitted])

    assert "subtitles" not in result[0]["evidence"]
