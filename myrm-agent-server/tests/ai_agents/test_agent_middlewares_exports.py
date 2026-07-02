"""Agent middleware export surface for GeneralAgent."""

from __future__ import annotations


def test_agent_middlewares_public_exports_exclude_auto_session_recall() -> None:
    from app.ai_agents import agent_middlewares

    exported = set(agent_middlewares.__all__)
    assert "memory_context_middleware" in exported
    assert "user_instructions_middleware" in exported
    assert "widget_capability_middleware" in exported
    assert "auto_session_recall_middleware" not in exported
