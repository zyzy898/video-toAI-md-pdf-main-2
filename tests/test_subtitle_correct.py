"""Tests for LLM subtitle correction pure helpers (asr.subtitle_correct)."""

from asr.subtitle_correct import (
    apply_corrections,
    build_correction_messages,
    chunk_lines,
    parse_correction_response,
)


def test_chunk_lines_indices_preserved():
    lines = [f"line{i}" for i in range(5)]
    batches = chunk_lines(lines, batch_size=2)
    assert [len(b) for b in batches] == [2, 2, 1]
    # global indices stay continuous across batches
    assert batches[0] == [(0, "line0"), (1, "line1")]
    assert batches[2] == [(4, "line4")]


def test_build_correction_messages_includes_glossary():
    batch = [(0, "这是铁子")]
    msgs = build_correction_messages(batch, glossary="帖子, 点赞")
    assert msgs[0]["role"] == "system"
    assert "帖子" in msgs[1]["content"]
    assert '"id": 0' in msgs[1]["content"]


def test_parse_correction_response_plain_json():
    reply = '{"corrections":[{"id":0,"text":"这是帖子"},{"id":1,"text":"点赞"}]}'
    out = parse_correction_response(reply)
    assert out == {0: "这是帖子", 1: "点赞"}


def test_parse_correction_response_with_code_fence():
    reply = '```json\n{"corrections":[{"id":2,"text":"在线"}]}\n```'
    assert parse_correction_response(reply) == {2: "在线"}


def test_parse_correction_response_malformed_returns_empty():
    assert parse_correction_response("not json at all") == {}
    assert parse_correction_response("") == {}
    assert parse_correction_response('{"foo":1}') == {}


def test_apply_corrections_fixes_homophone():
    lines = ["发一条铁子", "记得点赞"]
    new_lines, changed = apply_corrections(lines, {0: "发一条帖子"})
    assert new_lines == ["发一条帖子", "记得点赞"]
    assert changed == 1


def test_apply_corrections_rejects_rewrite():
    # Model tried to expand a short line into a long rewrite -> rejected.
    lines = ["铁子"]
    new_lines, changed = apply_corrections(
        lines, {0: "这是一段被模型大幅改写并扩写了很多内容的句子"}
    )
    assert new_lines == ["铁子"]
    assert changed == 0


def test_apply_corrections_ignores_out_of_range():
    lines = ["一", "二"]
    new_lines, changed = apply_corrections(lines, {5: "三"})
    assert new_lines == ["一", "二"]
    assert changed == 0


def test_apply_corrections_does_not_mutate_input():
    lines = ["铁子"]
    original = list(lines)
    apply_corrections(lines, {0: "帖子"})
    assert lines == original
