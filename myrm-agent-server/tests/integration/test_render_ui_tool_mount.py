"""Integration: render_ui / update_ui_data mount policy for inline A2UI surfaces."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.ai_agents.general_agent.tool_setup import (
    ToolSetupMixin,
    _should_mount_render_ui_tools,
)


def _tool_names(items: list[object]) -> set[str]:
    return {name for tool in items if (name := getattr(tool, "name", None))}


def _make_mixin(**overrides: object) -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    defaults: dict[str, object] = {
        "enable_web_search": False,
        "search_service_cfg": None,
        "reranker_config": None,
        "enable_advanced_retrieval": False,
        "embedding_config": None,
        "fetch_raw_webpage": False,
        "enable_render_ui": True,
        "image_generation_params": None,
        "video_generation_params": None,
        "tts_params": None,
        "search_depth": "normal",
        "model_cfg": MagicMock(model="test-model", api_key="k", base_url="http://localhost"),
        "skill_ids": [],
        "channel_name": "web_chat",
        "client_surface": "web",
        "declared_allowed_roots": (),
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(mixin, key, value)
    return mixin


def test_should_mount_predicate_matrix() -> None:
    assert _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface="web",
    )
    assert _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface="tauri",
    )
    assert not _should_mount_render_ui_tools(
        enable_render_ui=False,
        channel_name="web_chat",
        client_surface="web",
    )
    assert not _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="telegram_instance_1",
        client_surface="web",
    )
    assert not _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="cron",
        client_surface=None,
    )
    assert not _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface="headless",
    )


def test_render_ui_mounted_for_web_chat() -> None:
    mixin = _make_mixin()
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    assert "render_ui_tool" in _tool_names(tools)
    assert "update_ui_data_tool" in _tool_names(tools)


def test_render_ui_skipped_for_im_channel() -> None:
    mixin = _make_mixin(channel_name="telegram_abc123")
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    assert "render_ui_tool" not in _tool_names(tools)
    assert "update_ui_data_tool" not in _tool_names(tools)


def test_render_ui_skipped_for_cron_channel() -> None:
    mixin = _make_mixin(channel_name="cron")
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    assert "render_ui_tool" not in _tool_names(tools)


def test_render_ui_skipped_for_headless_surface() -> None:
    mixin = _make_mixin(client_surface="headless")
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    assert "render_ui_tool" not in _tool_names(tools)


def test_im_channel_entitlement_differs_from_mount() -> None:
    """Profile entitlement (active_tool_groups) stays on; mount gate blocks Turn1 tools."""
    from types import SimpleNamespace

    from app.ai_agents.general_agent.active_tool_groups import derive_active_tool_groups

    mixin = _make_mixin(channel_name="telegram_abc123")
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)
    assert "render_ui_tool" not in _tool_names(tools)

    agent = SimpleNamespace(
        enable_web_search=False,
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
        enable_render_ui=True,
        enable_structured_clarify=False,
        enable_external_cli=False,
        enable_cron_eager=False,
        image_generation_params=None,
        video_generation_params=None,
        tts_params=None,
    )
    groups = derive_active_tool_groups(agent, enable_planning=False)
    assert "render_ui" in groups
