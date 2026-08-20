"""Web search config-gap preflight dispatch tests for stream_chunks.py."""

from __future__ import annotations

from app.services.agent.stream_session.entitlement_gap_preflight import (
    build_web_search_config_gap_sse_event,
    reset_capability_gap_emission_tracker,
)


def _simulate_config_gap_preflight(
    *,
    resume_value: object | None,
    entitlement_preflight_text: str | None,
    web_search_profile_enabled: bool,
    enable_web_search: bool,
    search_is_user_configured: bool,
) -> list[dict[str, object]]:
    """Mirror stream_chunks config-gap + entitlement preflight split."""
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

    if entitlement_preflight_text:
        # Entitlement text gaps are orthogonal; this test focuses on config gap.
        pass

    return events


def test_web_search_config_gap_emits_when_preflight_text_empty() -> None:
    """Attachment-only sends have empty text but must still emit config gap."""
    events = _simulate_config_gap_preflight(
        resume_value=None,
        entitlement_preflight_text="",
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
        entitlement_preflight_text=None,
        web_search_profile_enabled=True,
        enable_web_search=False,
        search_is_user_configured=False,
    )
    assert events == []


def test_web_search_config_gap_none_when_runtime_enabled() -> None:
    events = _simulate_config_gap_preflight(
        resume_value=None,
        entitlement_preflight_text="search news",
        web_search_profile_enabled=True,
        enable_web_search=True,
        search_is_user_configured=True,
    )
    assert events == []
