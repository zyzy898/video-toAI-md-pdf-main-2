from services.source_url import (
    append_unique_url_candidate,
    build_source_url_candidates,
    extract_media_ids_from_text,
    extract_media_ids_from_url,
    extract_numeric_media_id,
    extract_video_urls_from_json_payload,
    looks_like_video_candidate_url,
    normalize_source_url,
    url_contains_media_id,
)


def test_normalize_source_url_extracts_url_from_surrounding_text():
    assert normalize_source_url("???? https://example.com/video.mp4?x=1 ??") == "https://example.com/video.mp4?x=1"


def test_normalize_source_url_adds_scheme_for_known_share_link():
    assert normalize_source_url("v.douyin.com/AbC_12/") == "https://v.douyin.com/AbC_12/"


def test_extract_numeric_media_id_strips_non_digits_and_requires_min_length():
    assert extract_numeric_media_id("aweme_id=12345678901") == "12345678901"
    assert extract_numeric_media_id("123") == ""


def test_build_source_url_candidates_adds_douyin_canonical_urls():
    candidates = build_source_url_candidates("https://www.douyin.com/video/12345678901")

    assert candidates == [
        "https://www.douyin.com/video/12345678901",
        "https://www.iesdouyin.com/share/video/12345678901/",
    ]


def test_append_unique_url_candidate_normalizes_protocol_relative_and_relative_urls():
    candidates: list[str] = []
    append_unique_url_candidate(candidates, "//cdn.example.com/video.mp4")
    append_unique_url_candidate(candidates, "/media/clip.mp4", base_url="https://example.com/page")
    append_unique_url_candidate(candidates, "//cdn.example.com/video.mp4")

    assert candidates == ["https://cdn.example.com/video.mp4", "https://example.com/media/clip.mp4"]


def test_extract_media_ids_from_text_and_url_dedupes_results():
    text = "aweme_id=12345678901 and /video/12345678901 plus item_id=98765432109"
    assert extract_media_ids_from_text(text) == ["12345678901", "98765432109"]
    assert extract_media_ids_from_url("https://www.douyin.com/video/12345678901?aweme_id=98765432109") == [
        "98765432109",
        "12345678901",
    ]


def test_url_contains_media_id_checks_query_and_path():
    assert url_contains_media_id("https://www.douyin.com/video/12345678901", "12345678901")
    assert not url_contains_media_id("https://www.douyin.com/video/12345678901", "98765432109")


def test_looks_like_video_candidate_url_recognizes_extensions_and_video_paths():
    assert looks_like_video_candidate_url("https://example.com/a.mp4?x=1")
    assert looks_like_video_candidate_url("https://www.douyin.com/share/video/12345678901/")
    assert not looks_like_video_candidate_url("https://example.com/page")


def test_extract_video_urls_from_json_payload_recurses_and_uses_base_url():
    collected: list[str] = []
    extract_video_urls_from_json_payload(
        {"items": [{"play_url": "/media/a.mp4"}, {"title": "ignored"}]},
        collected,
        base_url="https://example.com/page",
    )

    assert collected == ["https://example.com/media/a.mp4"]
