from datetime import datetime
from pathlib import Path

from services.path_builders import build_unique_upload_path, create_unique_output_dir


def test_build_unique_upload_path_sanitizes_name_and_avoids_collisions(tmp_path):
    (tmp_path / "unsafe.mp4").write_text("existing", encoding="utf-8")

    result = build_unique_upload_path("../unsafe.mp4", upload_root=tmp_path)

    assert result == tmp_path / "unsafe_1.mp4"
    assert not result.exists()


def test_build_unique_upload_path_uses_timestamped_fallback_for_empty_name(tmp_path):
    now = datetime(2026, 7, 9, 1, 2, 3)
    (tmp_path / "upload_20260709_010203.mp4").write_text("existing", encoding="utf-8")

    result = build_unique_upload_path("", upload_root=tmp_path, now=now)

    assert result == tmp_path / "upload_20260709_010203_1.mp4"


def test_build_unique_upload_path_preserves_non_ascii_name_extension(tmp_path):
    now = datetime(2026, 7, 9, 1, 2, 3)

    result = build_unique_upload_path("视频.mp4", upload_root=tmp_path, now=now)

    assert result == tmp_path / "upload_20260709_010203.mp4"
    assert result.suffix == ".mp4"


def test_create_unique_output_dir_sanitizes_stem_and_creates_directory(tmp_path):
    now = datetime(2026, 7, 9, 1, 2, 3)
    (tmp_path / "My_Clip_20260709_010203").mkdir()

    result = create_unique_output_dir(Path("../My Clip!.mp4"), output_root=tmp_path, now=now)

    assert result == tmp_path / "My_Clip_20260709_010203_1"
    assert result.is_dir()


def test_create_unique_output_dir_uses_video_fallback_for_empty_sanitized_stem(tmp_path):
    now = datetime(2026, 7, 9, 1, 2, 3)

    result = create_unique_output_dir(Path("\u4e2d\u6587.mp4"), output_root=tmp_path, now=now)

    assert result == tmp_path / "video_20260709_010203"
    assert result.is_dir()


def test_build_upload_staging_path_sanitizes_name_and_uses_token(tmp_path):
    from services.path_builders import build_upload_staging_path

    result = build_upload_staging_path(
        "../demo video.mov", staging_root=tmp_path, token="abc123"
    )

    assert result == tmp_path / "demo_video_abc123.mov"


def test_build_upload_staging_path_defaults_empty_suffix_to_mp4(tmp_path):
    from services.path_builders import build_upload_staging_path

    result = build_upload_staging_path("clip", staging_root=tmp_path, token="abc123")

    assert result == tmp_path / "clip_abc123.mp4"


def test_build_upload_staging_path_uses_timestamped_fallback_for_empty_name(tmp_path):
    from datetime import datetime
    from services.path_builders import build_upload_staging_path

    result = build_upload_staging_path(
        "",
        staging_root=tmp_path,
        token="abc123",
        now=datetime(2026, 7, 9, 1, 2, 3),
    )

    assert result == tmp_path / "staging_20260709_010203_abc123.mp4"


def test_reason_code_slug_normalizes_code_and_uses_fallback():
    from services.path_builders import reason_code_slug

    assert reason_code_slug("Policy-Violence/Adult") == "policy_violence_adult"
    assert reason_code_slug("") == "content_policy"


def test_build_unique_quarantine_path_creates_reason_dir_and_avoids_collisions(tmp_path):
    from datetime import datetime
    from services.path_builders import build_unique_quarantine_path

    now = datetime(2026, 7, 9, 1, 2, 3)
    reason_dir = tmp_path / "content_policy"
    reason_dir.mkdir()
    (reason_dir / "clip_20260709_010203.mp4").write_text("existing", encoding="utf-8")

    result = build_unique_quarantine_path(
        Path("clip.mp4"),
        quarantine_root=tmp_path,
        reason_code="content-policy",
        now=now,
    )

    assert result == reason_dir / "clip_20260709_010203_1.mp4"
    assert reason_dir.is_dir()
    assert not result.exists()


def test_find_cleanup_output_dirs_returns_legacy_and_timestamped_dirs_only(tmp_path):
    from services.path_builders import find_cleanup_output_dirs

    legacy = tmp_path / "clip"
    timestamped = tmp_path / "clip_20260709_010203"
    unrelated = tmp_path / "clipper_20260709_010203"
    file_match = tmp_path / "clip_20260709_010204"
    legacy.mkdir()
    timestamped.mkdir()
    unrelated.mkdir()
    file_match.write_text("not a dir", encoding="utf-8")

    result = find_cleanup_output_dirs("../clip.mp4", output_root=tmp_path)

    assert result == [legacy, timestamped]


def test_find_cleanup_output_dirs_returns_empty_for_invalid_filename(tmp_path):
    from services.path_builders import find_cleanup_output_dirs

    assert find_cleanup_output_dirs("", output_root=tmp_path) == []
