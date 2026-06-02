"""Test IM channel interrupt/resume data shapes for unified approval flow.

Verifies InboundMessage.resume_value and metadata used when resuming
after LangGraph interrupt() for IM channels (aligned with Web resume payload).
"""

from app.channels.types import InboundMessage


def test_inbound_message_has_resume_value_field() -> None:
    """InboundMessage accepts resume_value for Command(resume=...)."""
    msg = InboundMessage(
        channel="telegram",
        sender_id="user123",
        content="/approve",
        resume_value={"decisions": [{"type": "approve"}]},
    )

    assert msg.resume_value is not None
    assert msg.resume_value == {"decisions": [{"type": "approve"}]}


def test_inbound_message_resume_value_defaults_to_none() -> None:
    """Normal messages omit resume_value."""
    msg = InboundMessage(
        channel="telegram",
        sender_id="user123",
        content="Hello",
    )

    assert msg.resume_value is None


def test_approval_resume_message_shape() -> None:
    """Resume payload for approve matches router/executor expectations."""
    resume_value = {"decisions": [{"type": "approve"}]}

    msg = InboundMessage(
        channel="telegram",
        sender_id="user123",
        content="/approve",
        resume_value=resume_value,
        metadata={"is_resume": True},
    )

    assert msg.resume_value is not None
    assert msg.resume_value["decisions"][0]["type"] == "approve"
    assert msg.metadata.get("is_resume") is True


def test_denial_resume_message_shape() -> None:
    """Resume payload for reject matches router/executor expectations."""
    resume_value = {"decisions": [{"type": "reject"}]}

    msg = InboundMessage(
        channel="telegram",
        sender_id="user123",
        content="/deny",
        resume_value=resume_value,
        metadata={"is_resume": True},
    )

    assert msg.resume_value is not None
    assert msg.resume_value["decisions"][0]["type"] == "reject"
    assert msg.metadata.get("is_resume") is True


def test_batch_approval_resume_structure() -> None:
    """Multi-decision resume_value shape for batch tool approval."""
    resume_value = {
        "decisions": [
            {"type": "approve", "extensions": {"allowAlways": True}},
            {"type": "edit", "args": {"command": "ls -la"}},
            {"type": "reject", "feedback": "Too risky"},
        ]
    }

    msg = InboundMessage(
        channel="telegram",
        sender_id="user123",
        content="/approve",
        resume_value=resume_value,
    )

    assert len(msg.resume_value["decisions"]) == 3
    assert msg.resume_value["decisions"][0]["type"] == "approve"
    assert msg.resume_value["decisions"][1]["type"] == "edit"
    assert msg.resume_value["decisions"][2]["type"] == "reject"
