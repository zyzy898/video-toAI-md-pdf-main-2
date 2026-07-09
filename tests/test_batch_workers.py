from services.batch_workers import resolve_batch_analyze_workers


def test_resolve_batch_analyze_workers_uses_lowest_positive_cap():
    assert resolve_batch_analyze_workers(
        total_files=10,
        raw_workers="8",
        default_workers=2,
        cpu_count=4,
    ) == 4


def test_resolve_batch_analyze_workers_never_exceeds_file_count():
    assert resolve_batch_analyze_workers(
        total_files=2,
        raw_workers="8",
        default_workers=2,
        cpu_count=16,
    ) == 2


def test_resolve_batch_analyze_workers_falls_back_for_invalid_values():
    assert resolve_batch_analyze_workers(
        total_files=10,
        raw_workers="not-a-number",
        default_workers=3,
        cpu_count=16,
    ) == 3


def test_resolve_batch_analyze_workers_clamps_to_one_and_sixteen():
    assert resolve_batch_analyze_workers(
        total_files=10,
        raw_workers="0",
        default_workers=2,
        cpu_count=16,
    ) == 1
    assert resolve_batch_analyze_workers(
        total_files=100,
        raw_workers="999",
        default_workers=2,
        cpu_count=64,
    ) == 16


def test_resolve_batch_analyze_workers_treats_empty_file_or_cpu_counts_as_one():
    assert resolve_batch_analyze_workers(
        total_files=0,
        raw_workers="8",
        default_workers=2,
        cpu_count=0,
    ) == 1
