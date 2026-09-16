"""Web search config-gap preflight dispatch tests for stream_chunks.py."""

from __future__ import annotations

from app.services.agent.stream_session.entitlement_gap_preflight import (
    build_web_search_config_gap_sse_event,
    reset_capability_gap_emission_tracker,
)


def _simulate_config_gap_preflight(
    *,
    resume_value: object | None,
    web_search_profile_enabled: bool,
    enable_web_search: bool,
    search_is_user_configured: bool,
) -> list[dict[str, object]]:
    """Mirror the stream_chunks config-gap preflight branch."""
    reset_capability_gap_emission_tracker()
    events: list[dict[str, object]] = []

    if resume_value is None:
        search_gap_event = build_web_search_config_gap_sse_event(
            message_id="msg-1",
            web_search_profile_enabled=web_search_profile_enabled,
            enable_web_search=enable_web_search,
            search_is_user_configured=search_is_user_configured,
            chat_id="chat-1",
            locale="en",
        )
        if search_gap_event is not None:
            events.append(search_gap_event)

    return events


def test_web_search_config_gap_emits_for_attachment_only_send() -> None:
    """Attachment-only sends still emit the config gap (no user text required)."""
    events = _simulate_config_gap_preflight(
        resume_value=None,
        web_search_profile_enabled=True,
        enable_web_search=False,
        search_is_user_configured=False,
    )
    assert events, "expected capability_gap when web_search profile on but search unconfigured"
    data = events[0]["data"]
    assert isinstance(data, dict)
    assert data.get("tool_id") == "web_search"
    assert data.get("reason") == "not_configured"


def test_web_search_config_gap_skipped_on_resume() -> None:
    events = _simulate_config_gap_preflight(
        resume_value={"answer": "yes"},
        web_search_profile_enabled=True,
        enable_web_search=False,
        search_is_user_configured=False,
    )
    assert events == []


def test_web_search_config_gap_none_when_runtime_enabled() -> None:
    events = _simulate_config_gap_preflight(
        resume_value=None,
        web_search_profile_enabled=True,
        enable_web_search=True,
        search_is_user_configured=True,
    )
    assert events == []
