"""Unit tests for entitlement gap stream preflight."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.ai_agents.general_agent.active_tool_groups import (
    derive_active_tool_groups_from_params,
)
from app.services.agent.stream_session import entitlement_gap_preflight as preflight
from app.services.agent.stream_session.entitlement_gap_preflight import (
    CapabilityGapEmissionTracker,
    build_entitlement_gap_sse_event,
    build_web_search_config_gap_sse_event,
    reset_capability_gap_emission_tracker,
)


def _params(**overrides: object) -> SimpleNamespace:
    base = dict(
        enable_web_search=True,
        enable_browser=False,
        enable_file_ops=True,
        enable_shell_tools=True,
        enable_computer_use=False,
        enable_memory=True,
        incognito_mode=False,
        enable_conversation_search=False,
        enable_kanban=False,
        enable_wiki=False,
        enable_answer_tool=False,
        enable_render_ui=False,
        enable_structured_clarify=True,
        enable_cron_eager=False,
        enable_planning=False,
        image_generation=None,
        video_generation=None,
        tts=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def setup_function() -> None:
    reset_capability_gap_emission_tracker()


def test_derive_active_tool_groups_from_params_maps_media_fields() -> None:
    groups = derive_active_tool_groups_from_params(
        _params(enable_render_ui=True, image_generation=object()),
    )
    assert "render_ui" in groups
    assert "image_generation" in groups


def test_build_entitlement_gap_sse_event_render_ui_form_query() -> None:
    event = build_entitlement_gap_sse_event(
        message_id="msg-1",
        user_text="帮我填表准备 staging 部署配置",
        active_tool_groups=derive_active_tool_groups_from_params(_params()),
        chat_id="chat-1",
    )
    assert event is not None
    assert event["type"] == "capability_gap"
    data = event["data"]
    assert isinstance(data, dict)
    assert data["tool_id"] == "render_ui"
    assert data["tool_group"] == "render_ui"


def test_build_entitlement_gap_sse_event_none_when_group_enabled_on_web_chat() -> None:
    event = build_entitlement_gap_sse_event(
        message_id="msg-2",
        user_text="帮我填表",
        active_tool_groups=derive_active_tool_groups_from_params(
            _params(enable_render_ui=True)
        ),
        chat_id="chat-2",
        channel_name="web_chat",
        client_surface="web",
    )
    assert event is None


def test_build_entitlement_gap_sse_event_surface_unavailable_on_im_channel() -> None:
    event = build_entitlement_gap_sse_event(
        message_id="msg-im-1",
        user_text="帮我填表准备 staging 部署配置",
        active_tool_groups=derive_active_tool_groups_from_params(
            _params(enable_render_ui=True)
        ),
        chat_id="chat-im-1",
        channel_name="telegram",
        client_surface=None,
        locale="zh-CN",
    )
    assert event is not None
    assert event["type"] == "capability_gap"
    data = event["data"]
    assert isinstance(data, dict)
    assert data["tool_id"] == "render_ui"
    assert data["reason"] == "surface_unavailable"
    assert "Web 对话" in str(data["display_message"])


def test_build_entitlement_gap_sse_event_surface_unavailable_dedup() -> None:
    groups = derive_active_tool_groups_from_params(_params(enable_render_ui=True))
    first = build_entitlement_gap_sse_event(
        message_id="msg-im-2",
        user_text="帮我填表",
        active_tool_groups=groups,
        chat_id="chat-im-dedup",
        channel_name="telegram",
    )
    second = build_entitlement_gap_sse_event(
        message_id="msg-im-3",
        user_text="再帮我填表",
        active_tool_groups=groups,
        chat_id="chat-im-dedup",
        channel_name="telegram",
    )
    assert first is not None
    assert second is None


def test_build_entitlement_gap_sse_event_dedup_within_cooldown() -> None:
    groups = derive_active_tool_groups_from_params(_params())
    first = build_entitlement_gap_sse_event(
        message_id="msg-3",
        user_text="帮我填表",
        active_tool_groups=groups,
        chat_id="chat-dedup",
    )
    second = build_entitlement_gap_sse_event(
        message_id="msg-4",
        user_text="再帮我填表",
        active_tool_groups=groups,
        chat_id="chat-dedup",
    )
    assert first is not None
    assert second is None


def test_capability_gap_emission_tracker_re_emits_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = CapabilityGapEmissionTracker(cooldown_seconds=30.0)
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)

    assert tracker.should_emit("chat-cooldown", "render_ui") is True
    tracker.mark_emitted("chat-cooldown", "render_ui")
    assert tracker.should_emit("chat-cooldown", "render_ui") is False

    now = 1031.0
    assert tracker.should_emit("chat-cooldown", "render_ui") is True


def test_build_entitlement_gap_sse_event_re_emits_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_capability_gap_emission_tracker()
    monkeypatch.setattr(preflight, "_GAP_TOAST_COOLDOWN_SECONDS", 1.0)
    preflight._gap_emission_tracker = CapabilityGapEmissionTracker(cooldown_seconds=1.0)

    groups = derive_active_tool_groups_from_params(_params())
    first = build_entitlement_gap_sse_event(
        message_id="msg-5",
        user_text="帮我填表",
        active_tool_groups=groups,
        chat_id="chat-cooldown-emit",
    )
    second = build_entitlement_gap_sse_event(
        message_id="msg-6",
        user_text="帮我填表",
        active_tool_groups=groups,
        chat_id="chat-cooldown-emit",
    )
    assert first is not None
    assert second is None

    time.sleep(1.05)
    third = build_entitlement_gap_sse_event(
        message_id="msg-7",
        user_text="帮我填表",
        active_tool_groups=groups,
        chat_id="chat-cooldown-emit",
    )
    assert third is not None


def test_build_web_search_config_gap_not_configured() -> None:
    event = build_web_search_config_gap_sse_event(
        message_id="msg-search-1",
        web_search_profile_enabled=True,
        enable_web_search=False,
        search_is_user_configured=False,
        chat_id="chat-search-1",
        locale="en",
    )
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data["tool_id"] == "web_search"
    assert data["reason"] == "not_configured"
    assert data["settings_path"] == "/settings/search"


def test_build_web_search_config_gap_none_when_runtime_enabled() -> None:
    event = build_web_search_config_gap_sse_event(
        message_id="msg-search-2",
        web_search_profile_enabled=True,
        enable_web_search=True,
        search_is_user_configured=True,
        chat_id="chat-search-2",
        locale="en",
    )
    assert event is None


def test_resolve_web_search_config_gap_display_message_localized() -> None:
    from app.services.agent.stream_session.entitlement_gap_preflight import (
        resolve_web_search_config_gap_display_message,
    )

    en = resolve_web_search_config_gap_display_message(
        reason="not_configured", locale="en"
    )
    zh = resolve_web_search_config_gap_display_message(
        reason="not_configured", locale="zh"
    )
    unreachable = resolve_web_search_config_gap_display_message(
        reason="unreachable", locale="en"
    )

    assert "search API" in en
    assert "搜索" in zh
    assert "unreachable" in unreachable.lower() or "Check Settings" in unreachable
