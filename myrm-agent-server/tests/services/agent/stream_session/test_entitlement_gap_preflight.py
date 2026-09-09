"""Unit tests for entitlement gap stream preflight."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode

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
        file_access_mode=FileAccessMode.FULL,
        enable_shell_tools=True,
        enable_computer_use=False,
        enable_memory=True,
        incognito_mode=False,
        enable_conversation_search=False,
        enable_kanban=False,
        enable_wiki=False,
        enable_answer_tool=False,
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
        _params(image_generation=object()),
    )
    assert "image_generation" in groups


def test_build_entitlement_gap_sse_event_always_none() -> None:
    """Preflight returns None as dead surface-gap paths have been pruned."""
    event = build_entitlement_gap_sse_event(
        message_id="msg-1",
        user_text="帮我填表准备 staging 部署配置",
        active_tool_groups=derive_active_tool_groups_from_params(_params()),
        chat_id="chat-1",
        channel_name="telegram",
    )
    assert event is None


def test_capability_gap_emission_tracker_re_emits_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = CapabilityGapEmissionTracker(cooldown_seconds=30.0)
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)

    assert tracker.should_emit("chat-cooldown", "web_search:not_configured") is True
    tracker.mark_emitted("chat-cooldown", "web_search:not_configured")
    assert tracker.should_emit("chat-cooldown", "web_search:not_configured") is False

    now = 1031.0
    assert tracker.should_emit("chat-cooldown", "web_search:not_configured") is True


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

    zh = resolve_web_search_config_gap_display_message(reason="not_configured", locale="zh-CN")
    en = resolve_web_search_config_gap_display_message(reason="not_configured", locale="en")
    assert "未配置搜索 API" in zh
    assert "no search API is configured" in en
