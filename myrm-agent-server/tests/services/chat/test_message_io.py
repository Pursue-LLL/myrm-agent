"""Tests for compact.message_io — summary deserialization across the DB boundary.

``parse_existing_summary`` must survive all 14 ``StructuredSummary`` fields so
incremental compaction bases its merge on a complete prior summary, not a
5-field subset that silently drops constraints, pending asks, and next steps.
"""

from __future__ import annotations

import json

from app.services.chat.compact.message_io import parse_existing_summary


def test_parse_existing_summary_full_fields() -> None:
    payload = {
        "user_goal": "build feature",
        "completed_actions": ["step1"],
        "key_findings": ["found bug"],
        "errors_and_fixes": ["crash -> null check"],
        "files_modified": ["main.py"],
        "last_action": "fixed",
        "active_task": "add tests",
        "constraints_and_preferences": ["use TS"],
        "resolved_questions": ["Q -> A"],
        "pending_user_asks": ["update docs"],
        "active_state": "dev branch",
        "blocked_items": ["dep conflict"],
        "next_steps": ["run pytest"],
    }
    summary = parse_existing_summary(json.dumps(payload))
    assert summary is not None
    assert summary.user_goal == "build feature"
    assert summary.completed_actions == ["step1"]
    assert summary.key_findings == ["found bug"]
    assert summary.errors_and_fixes == ["crash -> null check"]
    assert summary.files_modified == ["main.py"]
    assert summary.last_action == "fixed"
    assert summary.active_task == "add tests"
    assert summary.constraints_and_preferences == ["use TS"]
    assert summary.resolved_questions == ["Q -> A"]
    assert summary.pending_user_asks == ["update docs"]
    assert summary.active_state == "dev branch"
    assert summary.blocked_items == ["dep conflict"]
    assert summary.next_steps == ["run pytest"]


def test_parse_existing_summary_missing_fields_default_empty() -> None:
    summary = parse_existing_summary('{"user_goal": "minimal"}')
    assert summary is not None
    assert summary.user_goal == "minimal"
    assert summary.completed_actions == []
    assert summary.blocked_items == []
    assert summary.next_steps == []


def test_parse_existing_summary_invalid_returns_none() -> None:
    assert parse_existing_summary("{not valid json") is None


def test_parse_existing_summary_roundtrip_keeps_blocked_and_next() -> None:
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        StructuredSummary,
    )

    original = StructuredSummary(
        user_goal="goal",
        completed_actions=["a"],
        blocked_items=["blocker"],
        next_steps=["next"],
        constraints_and_preferences=["c"],
        pending_user_asks=["p"],
    )
    parsed = parse_existing_summary(original.to_json())
    assert parsed is not None
    assert parsed.user_goal == "goal"
    assert parsed.blocked_items == ["blocker"]
    assert parsed.next_steps == ["next"]
    assert parsed.constraints_and_preferences == ["c"]
    assert parsed.pending_user_asks == ["p"]
