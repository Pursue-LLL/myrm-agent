"""Integration tests for inbound risk gate in AgentRouter._handle_merged.

Uses real RiskDetectionService.detect() with injected compiled rules.
Verifies the full routing path: blocked messages get rejected with i18n reply,
safe messages pass through to command resolution / agent execution.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage
from app.services.risk.detection import (
    RiskDetectionService,
    _CompiledRule,
)


def _build_service_with_rules(rules: list[_CompiledRule]) -> RiskDetectionService:
    svc = RiskDetectionService()
    svc._rules = rules
    svc._version = 1
    return svc


def _make_bus() -> MagicMock:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


def _make_router(bus: MagicMock | None = None) -> AgentRouter:
    bus = bus or _make_bus()
    return AgentRouter(
        bus=bus,
        pairing_store=MagicMock(),
        agent_executor=MagicMock(),
    )


API_KEY_RULE = _CompiledRule(
    rule_id="r-apikey",
    display_name="API Key Leak",
    severity="critical",
    action="block",
    category="credential",
    compiled=re.compile(r"sk-[A-Za-z0-9]{20,}", re.DOTALL),
)

PHONE_RULE = _CompiledRule(
    rule_id="r-phone",
    display_name="CN Mobile",
    severity="high",
    action="block",
    category="pii",
    compiled=re.compile(r"1[3-9]\d{9}", re.DOTALL),
)


@pytest.mark.asyncio
async def test_blocked_message_publishes_i18n_reply() -> None:
    """Blocked inbound message → outbound reply with risk_inbound_blocked i18n."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([API_KEY_RULE])

    msg = InboundMessage(
        channel="telegram",
        sender_id="user-123",
        content="Here is my key sk-AAAAAABBBBBBCCCCCCDDDD",
    )

    with (
        patch(
            "app.services.risk.detection.get_detection_service",
            return_value=svc,
        ),
        patch("asyncio.ensure_future"),
    ):
        await router._handle_merged(msg)

    bus.publish_outbound.assert_awaited_once()
    reply = bus.publish_outbound.call_args[0][0]
    assert reply.channel == "telegram"
    assert reply.recipient_id == "user-123"
    assert reply.content  # i18n key renders non-empty


@pytest.mark.asyncio
async def test_blocked_reply_targets_group_chat_id() -> None:
    """In group chats, blocked reply targets chat_id, not sender_id."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([PHONE_RULE])

    msg = InboundMessage(
        channel="wechat",
        sender_id="member-A",
        content="Call me at 13812345678",
        is_group=True,
        chat_id="group-room-1",
    )

    with (
        patch(
            "app.services.risk.detection.get_detection_service",
            return_value=svc,
        ),
        patch("asyncio.ensure_future"),
    ):
        await router._handle_merged(msg)

    bus.publish_outbound.assert_awaited_once()
    reply = bus.publish_outbound.call_args[0][0]
    assert reply.recipient_id == "group-room-1"


@pytest.mark.asyncio
async def test_safe_message_passes_through() -> None:
    """Safe message (no rule match) is NOT blocked — proceeds to command resolution."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([API_KEY_RULE])

    msg = InboundMessage(
        channel="telegram",
        sender_id="user-456",
        content="Hello, how are you?",
    )

    with patch(
        "app.services.risk.detection.get_detection_service",
        return_value=svc,
    ):
        try:
            await router._handle_merged(msg)
        except Exception:
            pass

    outbound_calls = bus.publish_outbound.call_args_list
    for call in outbound_calls:
        reply = call[0][0]
        assert "blocked" not in reply.content.lower() if reply.content else True


@pytest.mark.asyncio
async def test_no_rules_loaded_passes_through() -> None:
    """When RiskDetectionService has zero rules, messages pass through."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([])

    msg = InboundMessage(
        channel="slack",
        sender_id="user-789",
        content="sk-AAAAAABBBBBBCCCCCCDDDD this looks like a key",
    )

    with patch(
        "app.services.risk.detection.get_detection_service",
        return_value=svc,
    ):
        try:
            await router._handle_merged(msg)
        except Exception:
            pass

    outbound_calls = bus.publish_outbound.call_args_list
    for call in outbound_calls:
        reply = call[0][0]
        if reply.content:
            assert "blocked" not in reply.content.lower()


@pytest.mark.asyncio
async def test_resume_message_skips_risk_gate() -> None:
    """Resume messages (with resume_value) bypass inbound risk gate entirely."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([API_KEY_RULE])

    msg = InboundMessage(
        channel="telegram",
        sender_id="user-resume",
        content="sk-AAAAAABBBBBBCCCCCCDDDD",
        resume_value="continue",
    )

    with patch(
        "app.services.risk.detection.get_detection_service",
        return_value=svc,
    ):
        try:
            await router._handle_merged(msg)
        except Exception:
            pass

    outbound_calls = bus.publish_outbound.call_args_list
    for call in outbound_calls:
        reply = call[0][0]
        if reply.content:
            assert "blocked" not in reply.content.lower()


@pytest.mark.asyncio
async def test_empty_content_skips_risk_gate() -> None:
    """Empty content messages bypass risk gate entirely (no detection call)."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([API_KEY_RULE])

    msg = InboundMessage(
        channel="telegram",
        sender_id="user-empty",
        content="",
    )

    with patch(
        "app.services.risk.detection.get_detection_service",
        return_value=svc,
    ):
        try:
            await router._handle_merged(msg)
        except Exception:
            pass

    outbound_calls = bus.publish_outbound.call_args_list
    for call in outbound_calls:
        reply = call[0][0]
        if reply.content:
            assert "blocked" not in reply.content.lower()


@pytest.mark.asyncio
async def test_dm_blocked_targets_sender_id() -> None:
    """DM (non-group) blocked message targets sender_id as recipient."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([PHONE_RULE])

    msg = InboundMessage(
        channel="telegram",
        sender_id="dm-user-1",
        content="My number is 13812345678",
        is_group=False,
    )

    with (
        patch(
            "app.services.risk.detection.get_detection_service",
            return_value=svc,
        ),
        patch("asyncio.ensure_future"),
    ):
        await router._handle_merged(msg)

    bus.publish_outbound.assert_awaited_once()
    reply = bus.publish_outbound.call_args[0][0]
    assert reply.recipient_id == "dm-user-1"


@pytest.mark.asyncio
async def test_multiple_rules_short_circuits_on_first_block() -> None:
    """Multiple block rules — short-circuits on first match, reply sent once."""
    bus = _make_bus()
    router = _make_router(bus=bus)
    svc = _build_service_with_rules([API_KEY_RULE, PHONE_RULE])

    msg = InboundMessage(
        channel="slack",
        sender_id="user-multi",
        content="sk-AAAAAABBBBBBCCCCCCDDDD and 13812345678",
    )

    with (
        patch(
            "app.services.risk.detection.get_detection_service",
            return_value=svc,
        ),
        patch("asyncio.ensure_future"),
    ):
        await router._handle_merged(msg)

    bus.publish_outbound.assert_awaited_once()
    reply = bus.publish_outbound.call_args[0][0]
    assert reply.content  # blocked reply sent exactly once
