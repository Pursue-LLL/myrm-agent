from __future__ import annotations

import pytest

from app.services.project.assessment_import_service import parse_assessment_markdown


def test_parse_assessment_markdown_by_sections() -> None:
    content = """
## Milestone One
Scope summary.
- [ ] Task A
- [ ] Task B

## Milestone Two
- Task C
"""
    parsed = parse_assessment_markdown(content, fallback_title="Fallback")
    assert len(parsed) == 2
    assert parsed[0].title == "Milestone One"
    assert parsed[0].tasks == ["Task A", "Task B"]
    assert parsed[1].title == "Milestone Two"
    assert parsed[1].tasks == ["Task C"]


def test_parse_assessment_markdown_fallback_document_tasks() -> None:
    content = """
- [ ] Consolidate data source
- [ ] Build import route
"""
    parsed = parse_assessment_markdown(content, fallback_title="Assessment Plan")
    assert len(parsed) == 1
    assert parsed[0].title == "Assessment Plan"
    assert parsed[0].tasks == ["Consolidate data source", "Build import route"]


def test_parse_assessment_markdown_raises_when_no_tasks() -> None:
    content = """
## Notes
No actionable list items.
"""
    with pytest.raises(ValueError, match="does not contain importable"):
        parse_assessment_markdown(content, fallback_title="Assessment Plan")


def test_parse_assessment_markdown_rejects_non_actionable_checklist() -> None:
    content = """
## Context Digest
- [ ] Notes: summarize current progress
- [ ] Background: collect assumptions
"""
    with pytest.raises(ValueError, match="none are actionable tasks"):
        parse_assessment_markdown(content, fallback_title="Assessment Plan")


def test_parse_assessment_markdown_rejects_non_actionable_chinese_prefix() -> None:
    content = """
## 里程碑
- [ ] 说明：补充上下文
- [ ] 背景：整理输入来源
"""
    with pytest.raises(ValueError, match="none are actionable tasks"):
        parse_assessment_markdown(content, fallback_title="评估计划")


def test_parse_assessment_markdown_keeps_risk_mitigation_task() -> None:
    content = """
## Milestone Risk
- [ ] Risk mitigation plan for flaky API timeout
"""
    parsed = parse_assessment_markdown(content, fallback_title="Assessment Plan")
    assert parsed[0].tasks == ["Risk mitigation plan for flaky API timeout"]
