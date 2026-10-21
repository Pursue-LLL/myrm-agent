"""Tests for /learn skill_manage permission elevation over session presets."""

from __future__ import annotations

from app.core.channel_bridge.learn_handler import (
    apply_learn_skill_manage_permission_overlay,
    learn_authoring_prompt_text,
)
from app.services.agent.params.converter import _apply_session_preset

_LEARN_PROMPT = '[/learn] The user wants you to learn a reusable skill\n3. Save it with the `skill_manage_tool` (action="save").'


def test_learn_overlay_elevates_skill_manage_over_explore_preset() -> None:
    base: dict[str, object] = {"permissions": {"*": "allow", "skill_manage": "ask"}}
    explore = _apply_session_preset(base, "explore")
    assert isinstance(explore, dict)
    permissions = explore.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions["skill_manage"] == "deny"

    overlaid = apply_learn_skill_manage_permission_overlay(explore, query=_LEARN_PROMPT)
    assert isinstance(overlaid, dict)
    overlaid_permissions = overlaid.get("permissions")
    assert isinstance(overlaid_permissions, dict)
    assert overlaid_permissions["skill_manage"] == "ask"


def test_learn_overlay_noop_for_regular_chat() -> None:
    config: dict[str, object] = {"permissions": {"skill_manage": "deny"}}
    result = apply_learn_skill_manage_permission_overlay(
        config,
        query="Summarize this document",
    )
    assert result is config


def test_learn_authoring_prompt_text_accepts_multimodal_blocks() -> None:
    query: list[dict[str, str]] = [
        {"type": "text", "text": _LEARN_PROMPT},
    ]
    assert learn_authoring_prompt_text(query) == _LEARN_PROMPT
