"""Unit tests for criteria_parser.parse_markdown_criteria."""

from __future__ import annotations

from app.services.kanban.criteria_parser import _MAX_CRITERIA, parse_markdown_criteria


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
