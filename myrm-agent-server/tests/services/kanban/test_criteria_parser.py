"""Unit tests for criteria_parser.parse_markdown_criteria."""

from __future__ import annotations

from app.services.kanban.criteria_parser import (
    _MAX_CRITERIA,
    attach_completion_criteria,
    parse_markdown_criteria,
)


def test_empty_body_returns_empty() -> None:
    assert parse_markdown_criteria(None) == []
    assert parse_markdown_criteria("") == []
    assert parse_markdown_criteria("   \n  \n") == []


def test_unchecked_checkbox_lines_are_extracted() -> None:
    body = (
        "**Goal**\n"
        "Deliver a report.\n"
        "\n"
        "**Acceptance criteria**\n"
        "- [ ] Covers at least 5 competitors\n"
        "- [ ] Sources are linked\n"
    )
    assert parse_markdown_criteria(body) == [
        {"type": "semantic", "criteria": "Covers at least 5 competitors"},
        {"type": "semantic", "criteria": "Sources are linked"},
    ]


def test_checked_checkbox_lines_are_extracted_too() -> None:
    body = "- [x] Done item should still be an acceptance criterion\n"
    assert parse_markdown_criteria(body) == [
        {
            "type": "semantic",
            "criteria": "Done item should still be an acceptance criterion",
        }
    ]


def test_bold_and_numbered_prefixes_tolerated() -> None:
    body = (
        "1. [ ] Numbered line\n"
        "- [ ] **Bold text inside checklist**\n"
        "  1. [X] Nested checked line\n"
    )
    assert parse_markdown_criteria(body) == [
        {"type": "semantic", "criteria": "Numbered line"},
        {"type": "semantic", "criteria": "**Bold text inside checklist**"},
        {"type": "semantic", "criteria": "Nested checked line"},
    ]


def test_non_checklist_lines_ignored() -> None:
    body = (
        "not a checklist\n"
        "- just a list bullet (no checkbox)\n"
        "**Approach**\n"
        "- [ ] The only real criterion\n"
    )
    assert parse_markdown_criteria(body) == [
        {"type": "semantic", "criteria": "The only real criterion"}
    ]


def test_whitespace_checkbox_text_skipped() -> None:
    assert parse_markdown_criteria("- [ ]   \n") == []


def test_result_capped_at_max() -> None:
    body = "\n".join(f"- [ ] Criterion {i}" for i in range(12))
    criteria = parse_markdown_criteria(body)
    assert len(criteria) == _MAX_CRITERIA
    assert criteria[-1]["criteria"] == f"Criterion {_MAX_CRITERIA - 1}"


def test_schema_shape_is_semantic_dict() -> None:
    parsed = parse_markdown_criteria("- [ ] Ship it")
    assert parsed == [{"type": "semantic", "criteria": "Ship it"}]
    for item in parsed:
        assert set(item) == {"type", "criteria"}


# ---------------------------------------------------------------------------
# attach_completion_criteria
# ---------------------------------------------------------------------------


def test_attach_returns_merged_copy_with_criteria() -> None:
    meta = {"source_chat_id": "c1"}
    result = attach_completion_criteria(meta, "- [ ] Item A\n- [ ] Item B")
    assert result["completion_criteria"] == [
        {"type": "semantic", "criteria": "Item A"},
        {"type": "semantic", "criteria": "Item B"},
    ]
    # original dict untouched
    assert "completion_criteria" not in meta
    assert result["source_chat_id"] == "c1"


def test_attach_does_not_mutate_input() -> None:
    meta: dict[str, object] = {}
    attach_completion_criteria(meta, "- [ ] X")
    assert meta == {}


def test_attach_keeps_existing_criteria() -> None:
    meta: dict[str, object] = {"completion_criteria": "user text"}
    result = attach_completion_criteria(meta, "- [ ] LLM item")
    assert result is meta
    assert result["completion_criteria"] == "user text"


def test_attach_skips_when_no_checklist() -> None:
    meta: dict[str, object] = {"source_chat_id": "c1"}
    result = attach_completion_criteria(meta, "no checklist here")
    assert result is meta
    assert "completion_criteria" not in result
