from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from myrm_agent_harness.agent.middlewares._session_context import set_approval_session
from myrm_agent_harness.agent.middlewares.tooling._skill_failure_tracking import (
    _sanitize_error_message,
)
from myrm_agent_harness.agent.middlewares.tooling._skill_failure_tracking import (
    track_skill_execution as _track_skill_execution,
)
from myrm_agent_harness.agent.skill_agent.context import (
    add_loaded_skill,
    reset_loaded_skills,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.runtime.events import SkillFailureEvent


@dataclass(slots=True)
class _FakeEventBus:
    events: list[SkillFailureEvent] = field(default_factory=list)

    def publish(self, event: object) -> None:
        if isinstance(event, SkillFailureEvent):
            self.events.append(event)


def test_tool_failure_publishes_skill_failure_event(monkeypatch) -> None:
    fake_bus = _FakeEventBus()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.events.get_event_bus",
        lambda: fake_bus,
    )

    reset_loaded_skills()
    add_loaded_skill(
        SkillMetadata(
            name="sales_report_skill",
            description="Download and summarize sales reports.",
            storage_skill_id="skill-1",
            storage_path="/skills/sales_report/SKILL.md",
            version="4",
        )
    )

    set_approval_session("chat-skill-failure")
    try:
        _track_skill_execution(
            "browser_interact_tool",
            tool_call_id="call-1",
            tool_args={"selector": "#download"},
            success=False,
            error_message="Timeout: selector #download was not found",
        )
    finally:
        set_approval_session("")
        reset_loaded_skills()

    assert len(fake_bus.events) == 1
    event = fake_bus.events[0]
    assert event.tool_name == "browser_interact_tool"
    assert event.tool_call_id == "call-1"
    assert event.tool_args_hash
    assert event.error_signature.startswith("browser_interact_tool:")
    assert event.session_id == "chat-skill-failure"
    assert event.candidates[0].skill_id == "skill-1"
    assert event.candidates[0].confidence == 1.0


def test_tool_failure_without_storage_skill_is_ignored(monkeypatch) -> None:
    fake_bus = _FakeEventBus()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.events.get_event_bus",
        lambda: fake_bus,
    )

    reset_loaded_skills()
    add_loaded_skill(
        SkillMetadata(
            name="ephemeral_mcp_skill",
            description="MCP generated skill.",
        )
    )

    _track_skill_execution(
        "bash_code_execute_tool",
        tool_call_id="call-2",
        tool_args={"command": "missing-binary"},
        success=False,
        error_message="command not found: missing-binary",
    )

    reset_loaded_skills()

    assert fake_bus.events == []


def test_policy_block_does_not_publish_skill_failure_event(monkeypatch) -> None:
    fake_bus = _FakeEventBus()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.events.get_event_bus",
        lambda: fake_bus,
    )

    reset_loaded_skills()
    add_loaded_skill(
        SkillMetadata(
            name="sales_report_skill",
            description="Download and summarize sales reports.",
            storage_skill_id="skill-1",
        )
    )

    try:
        _track_skill_execution(
            "browser_interact_tool",
            tool_call_id="call-policy",
            tool_args={},
            success=False,
            error_message="E-Stop active: all tool execution is suspended",
            error_category="estop",
        )
    finally:
        reset_loaded_skills()

    assert fake_bus.events == []


def test_loop_guard_failure_publishes_loop_metadata(monkeypatch) -> None:
    fake_bus = _FakeEventBus()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.events.get_event_bus",
        lambda: fake_bus,
    )

    reset_loaded_skills()
    add_loaded_skill(
        SkillMetadata(
            name="browser_checkout_skill",
            description="Complete checkout workflow.",
            storage_skill_id="skill-loop",
        )
    )

    set_approval_session("chat-loop")
    try:
        _track_skill_execution(
            "browser_interact_tool",
            tool_call_id="call-loop",
            tool_args={"selector": "#pay"},
            success=False,
            error_message="Error: Tool called repeatedly with identical arguments",
            error_category="loop_guard",
            loop_kind="repetition",
        )
    finally:
        set_approval_session("")
        reset_loaded_skills()

    assert len(fake_bus.events) == 1
    event = fake_bus.events[0]
    assert event.loop_kind == "repetition"
    assert event.session_id == "chat-loop"


def test_multiple_storage_skills_candidates_have_confidence(monkeypatch) -> None:
    """Multiple storage skills → latest gets 0.65 confidence, others 0.25."""
    fake_bus = _FakeEventBus()
    monkeypatch.setattr(
        "myrm_agent_harness.runtime.events.get_event_bus",
        lambda: fake_bus,
    )
    reset_loaded_skills()
    add_loaded_skill(
        SkillMetadata(name="a", description="a", storage_skill_id="s1", version="1"),
    )
    add_loaded_skill(
        SkillMetadata(name="b", description="b", storage_skill_id="s2", version="2"),
    )
    try:
        _track_skill_execution(
            "tool",
            tool_call_id="c",
            tool_args={},
            success=False,
            error_message="boom",
        )
    finally:
        reset_loaded_skills()
    assert len(fake_bus.events) == 1
    confidences = {c.skill_id: c.confidence for c in fake_bus.events[0].candidates}
    assert confidences == {"s1": 0.25, "s2": 0.65}


def test_sanitize_error_message_redacts_long_tokens() -> None:
    secret = "sk-" + "a" * 40
    result = _sanitize_error_message(f"first line\nsecond {secret}\n{secret}")
    assert "a" * 40 not in result
    assert "<redacted>" in result


@pytest.mark.parametrize(
    ("error", "secret"),
    [
        ("401 for https://api.example.com/v1/x?api_key=sk_live_abc123def456", "sk_live_abc123def456"),
        ("403 with Authorization: Bearer abc123def456ghi", "abc123def456ghi"),
        ("FATAL password authentication failed, dsn=postgres://admin:hunter2pw@db.internal:5432/app", "hunter2pw"),
        ("denied; cookie: sessionid=a1b2c3d4e5f6", "a1b2c3d4e5f6"),
        # The two rules cover each other: the shared redaction cannot see these, the long-string rule can.
        (
            "S3 denied for key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY on bucket logs",
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        ),
        (
            "request failed id=3f2a9c1be84d4a0f9b7c6d5e4f3a2b1c0d9e8f7a (retry later)",
            "3f2a9c1be84d4a0f9b7c6d5e4f3a2b1c0d9e8f7a",
        ),
    ],
)
def test_sanitize_error_message_masks_labelled_and_unlabelled_secrets(error: str, secret: str) -> None:
    assert secret not in _sanitize_error_message(error)


def test_sanitize_error_message_keeps_plain_error_text_and_cuts_at_the_limit() -> None:
    assert (
        _sanitize_error_message("Timeout: selector #download was not found")
        == "Timeout: selector #download was not found"
    )
    assert len(_sanitize_error_message("failed" + " word" * 400)) == 1000


def test_hash_tool_args_covers_unserializable(monkeypatch) -> None:
    from myrm_agent_harness.agent.middlewares.tooling._skill_failure_tracking import (
        _hash_tool_args,
    )

    assert _hash_tool_args({"a": 1})
    assert _hash_tool_args({"x": object()})
