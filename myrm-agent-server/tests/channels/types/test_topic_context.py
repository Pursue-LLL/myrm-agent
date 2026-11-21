"""The agent that serves a topic is its bound agent unless the identity is frozen, and an empty agent id binds none."""

from __future__ import annotations

import pytest

from app.channels.types import TopicContext


@pytest.mark.parametrize(
    ("agent_id", "frozen", "expected"),
    [
        (None, False, None),
        ("", False, None),
        ("agent-a", False, "agent-a"),
        (None, True, None),
        ("", True, None),
        ("agent-a", True, None),
    ],
)
def test_a_frozen_identity_is_served_by_the_default_agent(agent_id: str | None, frozen: bool, expected: str | None) -> None:
    topic = TopicContext(topic_id="t", agent_id=agent_id, identity_revoked=frozen)

    assert topic.effective_agent_id == expected


def test_freezing_an_identity_keeps_the_stored_agent() -> None:
    topic = TopicContext(topic_id="t", agent_id="agent-a", identity_revoked=True)

    assert topic.agent_id == "agent-a"
