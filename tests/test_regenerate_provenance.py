import json
from pathlib import Path

import app


def _persisted_step():
    return {
        "step_id": "step_a",
        "step": 1,
        "time": "00:05",
        "time_seconds": 5.0,
        "title": "打开设置",
        "description": "进入设置页",
        "evidence": {
            "anchor_time_seconds": 5.0,
            "subtitles": [{"index": 1, "raw_text": "原字幕", "analyzed_text": "校正字幕"}],
            "screenshot": {
                "path": "images/step_01.jpg",
                "captured_at_seconds": 5.0,
            },
            "external_reference_ids": [],
        },
    }


def test_regenerate_uses_persisted_evidence_and_updates_template_metadata(tmp_path, monkeypatch):
    output_dir = tmp_path / "result"
    output_dir.mkdir()
    (output_dir / "steps.json").write_text(
        json.dumps([_persisted_step()], ensure_ascii=False),
        encoding="utf-8",
    )
    observed = {}
    history_records = [
        {
            "id": "history-1",
            "owner_id": "owner-a",
            "output_dir": str(output_dir),
            "output_template": "operation_guide",
            "external_references": [{"url": "https://old.example.com/"}],
        }
    ]

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.last_document_web_search_used = False

        async def generate_step_document(self, **kwargs):
            observed["steps"] = kwargs["steps"]
            observed["output_template"] = kwargs.get("output_template")
            Path(kwargs["output_path"]).write_text(
                "# 内容摘要\n\n## 核心摘要\n更新后摘要\n\n## 关键要点\n- 设置\n\n## 时间线\n- 00:08\n\n## 结论\n完成\n",
                encoding="utf-8",
            )

        def generate_pdf(self, _markdown_path, output_path):
            Path(output_path).write_bytes(b"pdf")

        def save_results(self, steps, output_path):
            Path(output_path).write_text(
                json.dumps(steps, ensure_ascii=False),
                encoding="utf-8",
            )

    submitted = _persisted_step()
    submitted["time"] = "00:08"
    submitted["time_seconds"] = 8.0
    submitted["evidence"]["screenshot"]["captured_at_seconds"] = 8.0

    monkeypatch.setattr(app, "_resolve_output_dir", lambda *_args, **_kwargs: output_dir)
    monkeypatch.setattr(
        app,
        "_read_shared_backend_model_options",
        lambda require_api_key=True: ("key", "model", "https://example.test/v1"),
    )
    monkeypatch.setattr(app, "VideoAnalyzerAgent", FakeAgent)
    monkeypatch.setattr(
        app,
        "_build_output_media_bundle",
        lambda *_args, **_kwargs: {"output_dir_name": output_dir.name},
    )
    monkeypatch.setattr(app.history_service, "read_unlocked", lambda: history_records)
    monkeypatch.setattr(
        app.history_service,
        "write_unlocked",
        lambda records: observed.setdefault("written_history", records),
    )

    response = app.app.test_client().post(
        "/regenerate",
        headers={"X-Client-ID": "owner-a"},
        json={
            "steps": [submitted],
            "output_dir": str(output_dir),
            "output_template": "content_summary",
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert observed["output_template"] == "content_summary"
    assert "subtitles" not in observed["steps"][0]["evidence"]
    assert "screenshot" not in observed["steps"][0]["evidence"]
    assert payload["output_template"] == "content_summary"
    assert payload["external_references"] == []
    assert observed["written_history"][0]["output_template"] == "content_summary"
    assert observed["written_history"][0]["external_references"] == []

