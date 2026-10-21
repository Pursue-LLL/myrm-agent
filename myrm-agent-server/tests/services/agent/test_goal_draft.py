"""Tests for goal draft spec normalization."""


def test_normalize_draft_parses_shell_and_semantic():
    from app.services.agent.goals.goal_draft import _normalize_draft

    raw = {
        "ui_summary": "Ship feature X",
        "constraints": [" Do not touch prod ", ""],
        "acceptance_criteria": [
            {"type": "shell", "command": "pytest -q", "timeout_seconds": 90},
            {"type": "semantic", "criteria": "Docs updated"},
            {"type": "shell", "command": ""},
            {"type": "unknown", "command": "skip"},
        ],
    }
    result = _normalize_draft(raw, "Build feature X with tests")
    assert result["ui_summary"] == "Ship feature X"
    assert result["constraints"] == ["Do not touch prod"]
    criteria = result["acceptance_criteria"]
    assert len(criteria) == 2
    assert criteria[0]["type"] == "shell"
    assert criteria[0]["timeout_seconds"] == 90
    assert criteria[1]["type"] == "semantic"


def test_parse_draft_json_from_markdown_fence():
    from app.services.agent.goals.goal_draft import _parse_draft_json

    text = 'Here you go:\n```json\n{"ui_summary": "A", "constraints": [], "acceptance_criteria": []}\n```'
    parsed = _parse_draft_json(text)
    assert parsed.get("ui_summary") == "A"


def test_parse_draft_json_unescaped_newline():
    from app.services.agent.goals.goal_draft import _parse_draft_json

    text = '{"ui_summary": "Ship\nfast", "constraints": [], "acceptance_criteria": []}'
    parsed = _parse_draft_json(text)
    assert parsed.get("ui_summary") == "Ship\nfast"


def test_parse_draft_json_picks_last_object():
    """格式示例对象在前、真实草稿在后时应取真实结果（最后者）。"""
    from app.services.agent.goals.goal_draft import _parse_draft_json

    text = (
        '```json\n{"ui_summary": "example", "constraints": [], "acceptance_criteria": []}\n```\n'
        'real draft:\n{"ui_summary": "A", "constraints": [], "acceptance_criteria": []}'
    )
    parsed = _parse_draft_json(text)
    assert parsed.get("ui_summary") == "A"


def test_parse_draft_json_garbage_returns_empty():
    from app.services.agent.goals.goal_draft import _parse_draft_json

    assert _parse_draft_json("no json at all") == {}
