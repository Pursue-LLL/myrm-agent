"""Unit tests for the follow-up suggestions parsing helper."""

from app.api.agents.suggestions import _parse_suggestions


def test_plain_array() -> None:
    assert _parse_suggestions('["q1", "q2", "q3"]') == ["q1", "q2", "q3"]


def test_fenced_array() -> None:
    raw = '```json\n["q1", "q2", "q3"]\n```'
    assert _parse_suggestions(raw) == ["q1", "q2", "q3"]


def test_prose_framing() -> None:
    raw = 'Here are follow-ups: ["q1", "q2", "q3"] Enjoy!'
    assert _parse_suggestions(raw) == ["q1", "q2", "q3"]


def test_unescaped_newline_in_string() -> None:
    raw = '["first line\nsecond", "plain"]'
    assert _parse_suggestions(raw) == ["first line\nsecond", "plain"]


def test_multiple_arrays_picks_last() -> None:
    """格式示例数组在前、真实结果在后时应取真实结果（最后者）。"""
    raw = '```json\n["example one"]\n```\nfinal:\n```json\n["real one", "real two", "real three"]\n```'
    assert _parse_suggestions(raw) == ["real one", "real two", "real three"]


def test_wrapped_in_object() -> None:
    raw = '{"suggestions": ["q1", "q2", "q3"]}'
    assert _parse_suggestions(raw) == ["q1", "q2", "q3"]


def test_suggestion_limit_cap() -> None:
    raw = '["1", "2", "3", "4", "5", "6", "7"]'
    assert len(_parse_suggestions(raw)) == 5


def test_line_based_fallback() -> None:
    raw = "1. First question\n2. Second question\n3. Third question"
    assert _parse_suggestions(raw) == [
        "First question",
        "Second question",
        "Third question",
    ]


def test_empty_and_garbage() -> None:
    assert _parse_suggestions("") == []
    # 无 JSON 时回退 line-based 提取：行长度 > 5 的文本仍会被返回（与原实现一致）
    assert _parse_suggestions("no json here") == ["no json here"]
