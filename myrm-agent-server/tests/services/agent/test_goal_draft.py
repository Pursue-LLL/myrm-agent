"""Tests for goal draft spec normalization."""


def test_normalize_draft_parses_shell_and_semantic():
    from app.services.agent.goal_draft import _normalize_draft

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
    from app.services.agent.goal_draft import _parse_draft_json

    text = 'Here you go:\n```json\n{"ui_summary": "A", "constraints": [], "acceptance_criteria": []}\n```'
    parsed = _parse_draft_json(text)
    assert parsed.get("ui_summary") == "A"
