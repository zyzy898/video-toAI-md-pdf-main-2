from services.video_filename import (
    extract_filename_from_content_disposition,
    guess_video_filename_from_url,
    safe_video_filename,
)


ALLOWED = {"mp4", "mov", "webm"}


def test_safe_video_filename_strips_path_traversal_and_forces_video_extension():
    assert safe_video_filename("../../etc/passwd", allowed_extensions=ALLOWED) == "etc_passwd.mp4"


def test_safe_video_filename_preserves_allowed_extension_case_insensitively():
    assert safe_video_filename("Clip.MOV", allowed_extensions=ALLOWED) == "Clip.mov"


def test_extract_filename_from_rfc5987_content_disposition():
    header = "attachment; filename*=UTF-8''lesson%20one.mp4"
    assert extract_filename_from_content_disposition(header) == "lesson one.mp4"


def test_guess_video_filename_prefers_content_disposition_filename():
    assert (
        guess_video_filename_from_url(
            "https://example.com/download?id=1",
            content_disposition='attachment; filename="lesson.webm"',
            allowed_extensions=ALLOWED,
        )
        == "lesson.webm"
    )


def test_guess_video_filename_uses_content_type_when_url_has_no_extension():
    assert (
        guess_video_filename_from_url(
            "https://example.com/download?id=1",
            content_type="video/mp4; charset=utf-8",
            fallback="fallback.mov",
            allowed_extensions=ALLOWED,
        )
        == "download.mp4"
    )


def test_guess_video_filename_falls_back_to_safe_mp4_for_unknown_extension():
    assert (
        guess_video_filename_from_url(
            "https://example.com/archive.bin",
            fallback="url_video.mp4",
            allowed_extensions=ALLOWED,
        )
        == "url_video.mp4"
    )
