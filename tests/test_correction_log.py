"""Tests for the correction feedback loop (asr.correction_log)."""

import json

from asr.correction_log import (
    append_glossary_terms,
    extract_term_pairs,
    harvest_terms,
    load_hotwords,
    record_and_learn,
    record_corrections,
    segment,
)


def test_extract_term_pairs_homophone_word_level():
    # The whole word should be captured, not just the single changed char.
    pairs = extract_term_pairs("发一条铁子", "发一条帖子")
    assert ("铁子", "帖子") in pairs


def test_extract_term_pairs_no_change_returns_empty():
    assert extract_term_pairs("完全一样", "完全一样") == []
    assert extract_term_pairs("有内容", "") == []


def test_extract_term_pairs_skips_single_char_noise():
    # Pure punctuation / single non-CJK change yields no useful term.
    pairs = extract_term_pairs("好的。", "好的，")
    assert pairs == []


def test_harvest_terms_collects_correct_side_deduped():
    changes = [
        {"original": "发个铁子", "corrected": "发个帖子"},
        {"original": "这个铁子不错", "corrected": "这个帖子不错"},
        {"original": "点击再现笔试", "corrected": "点击在线笔试"},
    ]
    terms = harvest_terms(changes)
    assert "帖子" in terms
    assert "在线" in terms
    # deduped: 帖子 appears once despite two source lines
    assert terms.count("帖子") == 1


def test_segment_returns_words():
    seg = segment("我要发帖子")
    assert isinstance(seg, list)
    assert "".join(seg) == "我要发帖子"


def test_append_glossary_dedupes(tmp_path):
    path = tmp_path / "glossary.txt"
    added1 = append_glossary_terms(["帖子", "点赞"], path=path)
    assert set(added1) == {"帖子", "点赞"}
    added2 = append_glossary_terms(["帖子", "在线"], path=path)
    assert added2 == ["在线"]  # 帖子 already present
    assert "帖子" in load_hotwords(path)
    assert "在线" in load_hotwords(path)


def test_record_corrections_writes_jsonl(tmp_path):
    log = tmp_path / "corr.jsonl"
    n = record_corrections(
        [{"time": "00:00:05,000", "original": "发个铁子", "corrected": "发个帖子"}],
        video="demo",
        path=log,
    )
    assert n == 1
    line = log.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["video"] == "demo"
    assert record["original"] == "发个铁子"
    assert record["corrected"] == "发个帖子"
    assert {"wrong": "铁子", "right": "帖子"} in record["term_pairs"]
    assert "original_seg" in record and "corrected_seg" in record


def test_record_corrections_skips_unchanged(tmp_path):
    log = tmp_path / "corr.jsonl"
    n = record_corrections(
        [{"original": "一样", "corrected": "一样"}], path=log
    )
    assert n == 0
    assert not log.exists()


def test_record_and_learn_writes_log_and_glossary(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBTITLE_CORRECTION_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("WHISPER_HOTWORDS_FILE", str(tmp_path / "glo.txt"))
    changes = [{"time": "00:01", "original": "发个铁子", "corrected": "发个帖子"}]
    written, added = record_and_learn(changes, video="v1")
    assert written == 1
    assert "帖子" in added
    assert (tmp_path / "log.jsonl").exists()
    assert "帖子" in (tmp_path / "glo.txt").read_text(encoding="utf-8")
