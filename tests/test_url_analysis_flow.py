from pathlib import Path

import app


def test_fallback_generated_subtitles_are_llm_corrected(tmp_path, monkeypatch):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "out"
    srt_path = output_dir / "clip.srt"

    class FakeAgent:
        def generate_subtitles(self, video_path, output_dir, cache_identity=None):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n发个铁子\n",
                encoding="utf-8",
            )
            return str(srt_path)

        def parse_srt(self, srt_path):
            return [{"start_seconds": 0, "start_time": "00:00:00,000", "text": "发个帖子"}]

    correction_calls = []
    monkeypatch.setattr(
        app,
        "_maybe_correct_subtitles",
        lambda agent, path, report=None: correction_calls.append(str(path)) or 1,
    )
    monkeypatch.setattr(
        app,
        "_build_subtitle_candidate_steps",
        lambda subtitles: (
            [{"step": 1, "time": "00:00", "title": "发帖", "description": "发个帖子"}],
            [{"time": "00:00", "text": "发帖"}],
        ),
    )

    steps, _meta, generated_srt = app._build_fallback_steps_when_empty(
        agent=FakeAgent(),
        video_path=video_path,
        output_dir=output_dir,
        srt_path=None,
        subtitle_cache_identity="sha256",
    )

    assert steps
    assert generated_srt == str(srt_path)
    assert correction_calls == [str(srt_path)]


def test_refresh_subtitle_runs_llm_correction(tmp_path, monkeypatch):
    output_dir = tmp_path / "result"
    output_dir.mkdir()
    video_path = output_dir / "clip.mp4"
    video_path.write_bytes(b"fake-video")
    srt_path = output_dir / "clip.srt"

    monkeypatch.setattr(app, "_resolve_output_dir", lambda output_dir_arg, must_exist=True: output_dir)
    monkeypatch.setattr(
        app.history_service,
        "read_unlocked",
        lambda: [{"output_dir": str(output_dir), "video_name": "clip.mp4"}],
    )
    monkeypatch.setattr(app, "_assert_within", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "_read_shared_backend_model_options",
        lambda require_api_key=True: ("test-key", "test-model", "https://example.test/v1"),
    )
    monkeypatch.setattr(app, "_normalize_processing_options", lambda data: ("base", True, False, 0, 1.0))

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def generate_subtitles(self, video_path, output_dir, cache_identity=None):
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n发个铁子\n",
                encoding="utf-8",
            )
            return str(srt_path)

    correction_calls = []
    monkeypatch.setattr(app, "VideoAnalyzerAgent", FakeAgent)
    monkeypatch.setattr(
        app,
        "_maybe_correct_subtitles",
        lambda agent, path, report=None: correction_calls.append(Path(path).name) or 1,
    )
    monkeypatch.setattr(
        app,
        "_build_output_media_bundle",
        lambda *args, **kwargs: {
            "video_file_name": "clip.mp4",
            "video_preview_url": "",
            "subtitle_available": True,
            "subtitle_exports": {},
        },
    )
    monkeypatch.setattr(
        app,
        "_parse_srt_file_entries",
        lambda subtitle_file: [{"index": 1, "text": "发个帖子"}],
    )

    response = app.app.test_client().post("/refresh_subtitle/result")

    assert response.status_code == 200
    assert correction_calls == ["clip.srt"]


def test_analyze_url_downloads_and_processes_video(tmp_path, monkeypatch):
    staging_path = tmp_path / "stage.mp4"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    saved_path = upload_dir / "downloaded.mp4"
    output_dir = tmp_path / "outputs" / "run1"
    output_dir.mkdir(parents=True)
    pdf_path = output_dir / "operation_guide.pdf"
    pdf_path.write_text("pdf", encoding="utf-8")

    def fake_download(source_url, target_path):
        target = Path(target_path)
        target.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32)
        return target, {
            "download_source": "platform_xiaohongshu_downloader_llm",
            "resolved_source_url": "https://example.com/resolved.mp4",
            "title": "下载标题",
        }

    processed = {}

    def fake_process_video(
        video_path,
        api_key,
        whisper_model,
        model_name,
        model_base_url,
        use_video,
        web_search,
        max_vision,
        fps,
        summary_only=False,
        output_template="operation_guide",
        history_owner_id="",
        progress_callback=None,
    ):
        processed["video_path"] = Path(video_path)
        processed["output_template"] = output_template
        return (
            [{"step": 1, "time": "00:00", "title": "开始", "description": "打开页面"}],
            "# doc",
            str(output_dir),
            str(pdf_path),
            True,
            {
                "result_mode": "steps",
                "output_media": {
                    "output_dir_name": output_dir.name,
                    "subtitle_available": True,
                    "subtitle_file_name": "downloaded.srt",
                },
            },
        )

    monkeypatch.setattr(app, "_assert_url_not_internal", lambda raw_url: None)
    monkeypatch.setattr(app, "_build_upload_staging_path", lambda filename: staging_path)
    monkeypatch.setattr(app, "_download_video_from_url", fake_download)
    monkeypatch.setattr(app, "is_valid_video_content", lambda path: True)
    monkeypatch.setattr(app, "_build_video_segment_policy", lambda path: {"requires_trim": False, "zone": "standard"})
    monkeypatch.setattr(app, "_check_upload_blacklist_precheck", lambda **kwargs: (None, "a" * 64))
    monkeypatch.setattr(
        app,
        "_run_upload_pre_risk_check",
        lambda **kwargs: ({"decision": "allow", "risk_level": "low"}, "a" * 64, "deferred"),
    )
    monkeypatch.setattr(app, "_build_unique_upload_path", lambda filename: saved_path)
    monkeypatch.setattr(app, "_mark_uploaded_video_loaded_now", lambda path: None)
    monkeypatch.setattr(
        app,
        "_read_shared_backend_model_options",
        lambda require_api_key=True: ("test-key", "test-model", "https://example.test/v1"),
    )
    monkeypatch.setattr(app, "_normalize_processing_options", lambda data: ("base", True, False, 10, 1.0))
    monkeypatch.setattr(
        app,
        "_apply_video_segment_processing_guardrails",
        lambda segment_policy, use_video, web_search, max_vision, summary_only: (
            use_video,
            web_search,
            max_vision,
            summary_only,
            [],
        ),
    )
    monkeypatch.setattr(app, "_update_single_progress", lambda **kwargs: None)
    monkeypatch.setattr(app, "process_video", fake_process_video)

    response = app.app.test_client().post(
        "/analyze_url",
        json={
            "url": "https://example.com/share/video",
            "output_template": "content_summary",
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert processed["video_path"] == saved_path
    assert processed["output_template"] == "content_summary"
    assert payload["output_template"] == "content_summary"
    assert payload["download_source"] == "platform_xiaohongshu_downloader_llm"
    assert payload["source_url"] == "https://example.com/share/video"
    assert payload["subtitle_available"] is True
