import json
from pathlib import Path

import app


def test_process_video_threads_template_and_persists_real_evidence(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    output_dir = tmp_path / "result"
    output_dir.mkdir()
    srt_path = output_dir / "clip.srt"
    observed = {}

    class FakeAgent:
        ffmpeg_cmd = "ffmpeg"

        def __init__(self, *args, **kwargs):
            self.last_document_web_search_used = False

        def generate_subtitles(self, _video_path, _output_dir, cache_identity=None):
            srt_path.write_text("RAW", encoding="utf-8")
            return str(srt_path)

        def parse_srt(self, _path):
            text = srt_path.read_text(encoding="utf-8")
            return [
                {
                    "index": 1,
                    "start_time": "00:00:01,000",
                    "end_time": "00:00:03,000",
                    "start_seconds": 1,
                    "end_seconds": 3,
                    "text": "打开原始菜单" if text == "RAW" else "打开设置菜单",
                }
            ]

        async def analyze_subtitles(self, _path):
            return [
                {
                    "step": 1,
                    "time": "00:01",
                    "title": "打开设置",
                    "description": "进入设置页",
                }
            ]

        def generate_screenshots_from_steps(self, _video_path, _steps, image_dir):
            Path(image_dir, "step_01.jpg").write_bytes(b"jpeg")

        async def generate_step_document(self, **kwargs):
            observed["output_template"] = kwargs.get("output_template")
            self.last_document_web_search_used = True
            Path(kwargs["output_path"]).write_text(
                "# 内容摘要\n\n## 参考资料\n- [官方文档](https://docs.example.com/guide)\n",
                encoding="utf-8",
            )

        def generate_pdf(self, _markdown_path, output_path):
            Path(output_path).write_bytes(b"pdf")

        def save_results(self, steps, output_path):
            observed["saved_steps"] = steps
            Path(output_path).write_text(
                json.dumps(steps, ensure_ascii=False),
                encoding="utf-8",
            )

    monkeypatch.setattr(app, "VideoAnalyzerAgent", FakeAgent)
    monkeypatch.setattr(app, "_create_unique_output_dir", lambda _path: output_dir)
    monkeypatch.setattr(app, "_compute_video_fingerprint_safely", lambda *_args: "a" * 64)
    monkeypatch.setattr(app, "_match_blacklisted_video_fingerprint_by_hash", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_build_upload_risk_model_cache_key_from_agent", lambda _agent: "model")
    monkeypatch.setattr(
        app,
        "_get_cached_upload_risk_result",
        lambda *_args: {
            "decision": "allow",
            "risk_level": "low",
            "reason_code": "SAFE_CONTENT",
        },
    )
    monkeypatch.setattr(app, "generate_web_preview_video", lambda **_kwargs: (False, {}))
    monkeypatch.setattr(
        app,
        "_prepare_long_video_analysis_source",
        lambda **_kwargs: (video_path, {"used": False}),
    )
    monkeypatch.setattr(
        app,
        "_maybe_correct_subtitles",
        lambda _agent, path, report=None: Path(path).write_text("CORRECTED", encoding="utf-8"),
    )
    monkeypatch.setattr(
        app,
        "_build_output_media_bundle",
        lambda *_args, **_kwargs: {"output_dir_name": output_dir.name},
    )
    monkeypatch.setattr(app, "save_history", lambda record, owner_id="": observed.setdefault("history", record))

    steps, _markdown, _output_dir, _pdf, has_steps, result_meta = (
        app.VideoProcessingService().process_video(
            video_path=video_path,
            api_key="key",
            whisper_model="base",
            model_name="model",
            model_base_url="https://example.test/v1",
            use_video=False,
            web_search=True,
            max_vision=0,
            output_template="content_summary",
        )
    )

    assert has_steps is True
    assert observed["output_template"] == "content_summary"
    assert steps == observed["saved_steps"]
    assert steps[0]["step_id"]
    assert steps[0]["time_seconds"] == 1.0
    assert steps[0]["evidence"]["subtitles"][0]["raw_text"] == "打开原始菜单"
    assert steps[0]["evidence"]["subtitles"][0]["analyzed_text"] == "打开设置菜单"
    assert steps[0]["evidence"]["screenshot"] == {
        "path": "images/step_01.jpg",
        "captured_at_seconds": 1.0,
    }
    assert result_meta["output_template"] == "content_summary"
    assert result_meta["external_references"][0]["url"] == "https://docs.example.com/guide"
    assert observed["history"]["output_template"] == "content_summary"
    assert observed["history"]["external_references"] == result_meta["external_references"]

