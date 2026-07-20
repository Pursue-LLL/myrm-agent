"""Unit tests for active_tool_groups SSOT (Entitlement Gap)."""

from __future__ import annotations

from types import SimpleNamespace

from app.ai_agents.general_agent.active_tool_groups import (
    ACTIVE_TOOL_GROUP_KEYS,
    derive_active_tool_groups,
)


def _agent(**overrides: object) -> SimpleNamespace:
    base = dict(
        enable_web_search=True,
        enable_browser=False,
        enable_file_ops=True,
        enable_code_execute=True,
        enable_computer_use=False,
        enable_memory=True,
        incognito_mode=False,
        enable_conversation_search=False,
        enable_kanban=False,
        enable_wiki=False,
        enable_answer_tool=False,
        enable_render_ui=False,
        enable_structured_clarify=False,
        enable_external_cli=False,
        enable_cron_eager=False,
        image_generation_params=None,
        video_generation_params=None,
        tts_params=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_active_tool_group_keys_match_derive_tuple_length() -> None:
    agent = _agent(
        enable_browser=True,
        enable_render_ui=True,
        enable_computer_use=True,
        enable_kanban=True,
        enable_wiki=True,
        enable_answer_tool=True,
        enable_structured_clarify=True,
        enable_external_cli=True,
        enable_cron_eager=True,
        enable_conversation_search=True,
        image_generation_params=object(),
        video_generation_params=object(),
        tts_params=object(),
    )
    groups = derive_active_tool_groups(agent, enable_planning=True)
    assert len(groups) == len(ACTIVE_TOOL_GROUP_KEYS)
    assert set(groups) == set(ACTIVE_TOOL_GROUP_KEYS)


def test_derive_includes_render_ui_when_enabled() -> None:
    groups = derive_active_tool_groups(_agent(enable_render_ui=True), enable_planning=False)
    assert "render_ui" in groups


def test_derive_excludes_render_ui_when_disabled() -> None:
    groups = derive_active_tool_groups(_agent(enable_render_ui=False), enable_planning=False)
    assert "render_ui" not in groups


def test_derive_includes_external_cli_when_enabled() -> None:
    groups = derive_active_tool_groups(
        _agent(enable_external_cli=True),
        enable_planning=False,
    )
    assert "external_cli" in groups


def test_derive_active_tool_groups_from_params_includes_external_cli() -> None:
    from app.ai_agents.general_agent.active_tool_groups import (
        derive_active_tool_groups_from_params,
    )

    params = SimpleNamespace(
        enable_web_search=False,
        enable_external_cli=True,
        enable_planning=False,
    )
    groups = derive_active_tool_groups_from_params(params)
    assert "external_cli" in groups
    groups = derive_active_tool_groups(_agent(enable_cron_eager=True), enable_planning=False)
    assert "cron" in groups


def test_derive_excludes_cron_when_eager_disabled() -> None:
    groups = derive_active_tool_groups(_agent(enable_cron_eager=False), enable_planning=False)
    assert "cron" not in groups


def test_derive_media_groups_from_params_presence() -> None:
    groups = derive_active_tool_groups(
        _agent(
            image_generation_params={"model": "dall-e"},
            video_generation_params={"provider": "openai"},
            tts_params={"model": "tts-1"},
        ),
        enable_planning=False,
    )
    assert "image_generation" in groups
    assert "video_generation" in groups
    assert "tts" in groups


def test_incognito_excludes_memory_and_conversation_history() -> None:
    groups = derive_active_tool_groups(
        _agent(incognito_mode=True, enable_conversation_search=True),
        enable_planning=False,
    )
    assert "memory" not in groups
    assert "conversation_history" not in groups


def test_conversation_history_requires_explicit_flag() -> None:
    groups = derive_active_tool_groups(_agent(enable_conversation_search=False), enable_planning=False)
    assert "conversation_history" not in groups
    groups_on = derive_active_tool_groups(_agent(enable_conversation_search=True), enable_planning=False)
    assert "conversation_history" in groups_on


def test_memory_off_excludes_conversation_history_even_when_flag_on() -> None:
    groups = derive_active_tool_groups(
        _agent(enable_memory=False, enable_conversation_search=True),
        enable_planning=False,
    )
    assert "memory" not in groups
    assert "conversation_history" not in groups


def test_builtin_tool_id_to_group_values_subset_of_active_keys() -> None:
    from myrm_agent_harness.agent.meta_tools.discover_capability.capability_gap import (
        BUILTIN_TOOL_ID_TO_GROUP,
    )

    assert set(BUILTIN_TOOL_ID_TO_GROUP.values()).issubset(set(ACTIVE_TOOL_GROUP_KEYS))


def test_builtin_tool_id_to_group_keys_match_togglable_catalog() -> None:
    from myrm_agent_harness.agent.meta_tools.discover_capability.capability_gap import (
        BUILTIN_TOOL_ID_TO_GROUP,
        CAPABILITY_GAP_REGISTRY,
    )

    from app.services.agent.builtin_tool_ids import TOGGLABLE_BUILTIN_TOOL_IDS

    registry_ids = {entry.tool_id for entry in CAPABILITY_GAP_REGISTRY}
    assert registry_ids == set(BUILTIN_TOOL_ID_TO_GROUP)
    assert set(BUILTIN_TOOL_ID_TO_GROUP) == set(TOGGLABLE_BUILTIN_TOOL_IDS)
    for entry in CAPABILITY_GAP_REGISTRY:
        assert BUILTIN_TOOL_ID_TO_GROUP[entry.tool_id] == entry.tool_group
        assert entry.triggers, f"capability gap triggers must be non-empty for {entry.tool_id!r}"
