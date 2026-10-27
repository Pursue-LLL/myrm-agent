"""Tests for how the ACP callback handler answers an agent's permission requests."""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.acp.core.event_bus import EventBus
from myrm_agent_harness.toolkits.acp.runtime.acp_callback import AcpCallbackHandler
from myrm_agent_harness.toolkits.acp.types import PermissionDecision, RuntimeConfig, RuntimeEvent


class TestAcpCallbackHandlerPermission:
    @pytest.mark.asyncio
    async def test_request_permission_ask_mode_waits_for_future(self) -> None:
        bus = EventBus()
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="ask"),
            "test-session",
            event_bus=bus,
            permission_request_timeout=0.5,
        )
        received: list[dict[str, object]] = []

        async def on_event(event: RuntimeEvent) -> None:
            received.append(event.data)
            future = event.data.get("response_future")
            if isinstance(future, asyncio.Future):
                future.set_result(PermissionDecision.ALLOW_ONCE)

        bus.subscribe(callback=on_event)
        options = [
            {"kind": "allow_once", "optionId": "allow_once"},
            {"kind": "reject_once", "optionId": "reject_once"},
        ]

        result = await handler.request_permission(options, "test-session", {"name": "Write", "path": "/tmp"})

        assert result == {"outcome": {"outcome": "selected", "optionId": "allow_once"}}
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_request_permission_ask_mode_times_out_to_deny(self) -> None:
        bus = EventBus()
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="ask"),
            "test-session",
            event_bus=bus,
            permission_request_timeout=0.001,
        )

        options = [
            {"kind": "allow_once", "optionId": "allow_once"},
            {"kind": "reject_once", "optionId": "reject_once"},
        ]
        result = await handler.request_permission(options, "test-session", {"name": "Write", "path": "/tmp"})

        assert result["outcome"]["outcome"] == "selected"
        assert result["outcome"]["optionId"] == "reject_once"

    @pytest.mark.asyncio
    async def test_request_permission_ask_mode_without_bus_falls_back_to_deny(
        self,
    ) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="ask"),
            "test-session",
        )
        options = [{"kind": "allow_once", "optionId": "allow_once"}]
        result = await handler.request_permission(options, "test-session", {"name": "Write", "path": "/tmp"})

        assert result["outcome"]["outcome"] == "cancelled"


class TestAcpCallbackHandlerPermissionModes:
    @pytest.mark.asyncio
    async def test_safe_mode_allows_read_ops(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="safe"),
            "s1",
        )
        options = [
            {"kind": "allow_once", "optionId": "allow_once"},
            {"kind": "reject_once", "optionId": "reject_once"},
        ]
        result = await handler.request_permission(options, "s1", {"name": "read_file"})
        assert result["outcome"]["optionId"] == "allow_once"

    @pytest.mark.asyncio
    async def test_safe_mode_rejects_write_ops(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="safe"),
            "s1",
        )
        options = [
            {"kind": "allow_once", "optionId": "allow_once"},
            {"kind": "reject_once", "optionId": "reject_once"},
        ]
        result = await handler.request_permission(options, "s1", {"name": "Write"})
        assert result["outcome"]["optionId"] == "reject_once"

    @pytest.mark.asyncio
    async def test_bypass_mode(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="bypass"),
            "s1",
        )
        options = [{"kind": "allow_always", "optionId": "allow_always"}]
        result = await handler.request_permission(options, "s1", {"name": "Write"})
        assert result["outcome"]["optionId"] == "allow_always"

    @pytest.mark.asyncio
    async def test_allow_all_mode(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="allow_all"),
            "s1",
        )
        options = [
            {"kind": "allow_once", "optionId": "allow_once"},
            {"kind": "allow_always", "optionId": "allow_always"},
        ]
        result = await handler.request_permission(options, "s1", {"name": "Write"})
        assert result["outcome"]["outcome"] == "selected"

    @pytest.mark.asyncio
    async def test_safe_mode_no_reject_option_cancels(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", permission_mode="safe"),
            "s1",
        )
        options = [{"kind": "allow_once", "optionId": "allow_once"}]
        result = await handler.request_permission(options, "s1", {"name": "Write"})
        assert result["outcome"]["outcome"] == "cancelled"
