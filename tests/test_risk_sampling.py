from pathlib import Path

from services.risk_sampling import (
    build_risk_timestamps,
    resolve_risk_frame_count,
    stable_risk_sampling_seed,
)


PARAMS = dict(
    default_max_frames=5,
    min_frames=3,
    dynamic_max_frames=8,
    growth_start_seconds=20,
    growth_every_seconds=45,
)


def test_no_duration_uses_fixed_base_timestamps_clipped_to_frame_count():
    assert build_risk_timestamps(4, video_duration_seconds=None, **PARAMS) == [0, 2, 5, 10]


def test_long_duration_grows_frame_count_but_clamps_to_dynamic_max():
    assert resolve_risk_frame_count(5, 500.0, **PARAMS) == 8


def test_sampling_is_deterministic_for_same_file_duration_and_count(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")

    first = build_risk_timestamps(5, video_duration_seconds=120.0, video_path=video_path, **PARAMS)
    second = build_risk_timestamps(5, video_duration_seconds=120.0, video_path=video_path, **PARAMS)

    assert first == second


def test_sampling_returns_sorted_unique_timestamps_within_video_duration(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")

    timestamps = build_risk_timestamps(5, video_duration_seconds=120.0, video_path=video_path, **PARAMS)

    assert timestamps == sorted(timestamps)
    assert len(timestamps) == len(set(timestamps)) == 7
    assert all(0 <= timestamp <= 119 for timestamp in timestamps)


def test_sampling_handles_missing_video_path_stat_deterministically(tmp_path):
    missing_path = tmp_path / "missing.mp4"

    first_seed = stable_risk_sampling_seed(missing_path, 30.0, 5)
    second_seed = stable_risk_sampling_seed(missing_path, 30.0, 5)
    assert first_seed == second_seed

    first = build_risk_timestamps(5, video_duration_seconds=30.0, video_path=missing_path, **PARAMS)
    second = build_risk_timestamps(5, video_duration_seconds=30.0, video_path=missing_path, **PARAMS)
    assert first == second


def test_short_duration_does_not_request_more_unique_seconds_than_exist():
    assert build_risk_timestamps(5, video_duration_seconds=2.0, **PARAMS) == [0, 1]
