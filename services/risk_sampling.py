import hashlib
import random
from pathlib import Path

from utils import _safe_int

_FALLBACK_RISK_TIMESTAMPS = [0, 2, 5, 10, 15, 25, 35, 50, 70, 95, 125, 160, 200, 245, 295]


def resolve_risk_frame_count(
    max_frames: int,
    video_duration_seconds: float | None,
    *,
    default_max_frames: int,
    min_frames: int,
    dynamic_max_frames: int,
    growth_start_seconds: int,
    growth_every_seconds: int,
) -> int:
    """Resolve how many frames should be sampled for risk moderation."""
    base_count = _safe_int(max_frames, default_max_frames, min_frames, dynamic_max_frames)
    if video_duration_seconds is None or video_duration_seconds <= 0:
        return base_count

    growth_source = max(0.0, float(video_duration_seconds) - growth_start_seconds)
    bonus_frames = int(growth_source // growth_every_seconds)
    return _safe_int(base_count + bonus_frames, base_count, min_frames, dynamic_max_frames)


def stable_risk_sampling_seed(
    video_path: Path | None,
    video_duration_seconds: float | None,
    frame_count: int,
) -> int:
    """Build a deterministic sampling seed from stable video metadata."""
    path_text = str(video_path or "")
    size = 0
    mtime_ns = 0
    if video_path is not None:
        try:
            stat_info = video_path.stat()
            size = int(getattr(stat_info, "st_size", 0))
            mtime_ns = int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1e9)))
        except OSError:
            pass

    duration_text = "none" if video_duration_seconds is None else f"{float(video_duration_seconds):.3f}"
    seed_text = f"{path_text}|{size}|{mtime_ns}|{duration_text}|{frame_count}"
    digest = hashlib.sha256(seed_text.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:16], 16)


def build_risk_timestamps(
    max_frames: int,
    *,
    video_duration_seconds: float | None = None,
    video_path: Path | None = None,
    default_max_frames: int,
    min_frames: int,
    dynamic_max_frames: int,
    growth_start_seconds: int,
    growth_every_seconds: int,
) -> list[int]:
    """Return deterministic, sorted, unique timestamps for video risk sampling."""
    frame_count = resolve_risk_frame_count(
        max_frames,
        video_duration_seconds,
        default_max_frames=default_max_frames,
        min_frames=min_frames,
        dynamic_max_frames=dynamic_max_frames,
        growth_start_seconds=growth_start_seconds,
        growth_every_seconds=growth_every_seconds,
    )
    if video_duration_seconds is None or video_duration_seconds <= 0:
        return _FALLBACK_RISK_TIMESTAMPS[:frame_count]

    max_second = max(1, int(video_duration_seconds) - 1)
    target_count = min(frame_count, max_second + 1)
    seed = stable_risk_sampling_seed(video_path, video_duration_seconds, target_count)
    rng = random.Random(seed)

    timestamps: list[int] = []
    for idx in range(target_count):
        segment_start = int((idx * max_second) / target_count)
        segment_end = int(((idx + 1) * max_second) / target_count)
        if idx == target_count - 1:
            segment_end = max_second
        if segment_end < segment_start:
            segment_end = segment_start
        if segment_end == segment_start:
            sample = segment_start
        else:
            sample = rng.randint(segment_start, segment_end)
        timestamps.append(sample)

    unique_sorted = sorted(set(max(0, min(max_second, int(ts))) for ts in timestamps))
    while len(unique_sorted) < target_count:
        candidate = rng.randint(0, max_second)
        if candidate in unique_sorted:
            continue
        unique_sorted.append(candidate)
        unique_sorted.sort()

    return unique_sorted[:target_count]
