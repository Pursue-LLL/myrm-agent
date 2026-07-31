"""Tests for MCP elicitation handler — MRTR → ApprovalRegistry bridge."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.backends.mcp_elicitation_handler import (
    _normalize_decision,
    _pending_elicitations,
    build_mcp_elicitation_handler,
    resolve_pending_elicitation,
)


class TestNormalizeDecision:
    """Map approval UI decisions to MCP elicitation actions."""

    def test_approve_maps_to_accept(self) -> None:
        assert _normalize_decision("approve") == "accept"

    def test_approved_maps_to_accept(self) -> None:
        assert _normalize_decision("approved") == "accept"

    def test_deny_maps_to_decline(self) -> None:
        assert _normalize_decision("deny") == "decline"

    def test_denied_maps_to_decline(self) -> None:
        assert _normalize_decision("denied") == "decline"

    def test_reject_maps_to_decline(self) -> None:
        assert _normalize_decision("reject") == "decline"

    def test_rejected_maps_to_decline(self) -> None:
        assert _normalize_decision("rejected") == "decline"

    def test_cancel_maps_to_cancel(self) -> None:
        assert _normalize_decision("cancel") == "cancel"
        assert _normalize_decision("cancelled") == "cancel"
        assert _normalize_decision("timeout") == "cancel"

    def test_unknown_defaults_to_decline(self) -> None:
        assert _normalize_decision("unknown") == "decline"
        assert _normalize_decision("") == "decline"
        assert _normalize_decision("maybe") == "decline"


class TestResolvePendingElicitation:
    """Wake a suspended handler with the user's decision."""

    def test_resolve_existing_entry(self) -> None:
        event = asyncio.Event()
        _pending_elicitations["test-id"] = (event, "decline")
        try:
            result = resolve_pending_elicitation("test-id", "approve")
            assert result is True
            assert event.is_set()
            _, decision = _pending_elicitations["test-id"]
            assert decision == "approve"
        finally:
            _pending_elicitations.pop("test-id", None)

    def test_resolve_nonexistent_entry(self) -> None:
        result = resolve_pending_elicitation("nonexistent-id", "approve")
        assert result is False

    def test_resolve_sets_event(self) -> None:
        event = asyncio.Event()
        _pending_elicitations["wake-id"] = (event, "decline")
        try:
            assert not event.is_set()
            resolve_pending_elicitation("wake-id", "deny")
            assert event.is_set()
        finally:
            _pending_elicitations.pop("wake-id", None)


class TestBuildMCPElicitationHandler:
    """Factory that returns an async handler conforming to harness protocol."""

    @pytest.mark.asyncio
    async def test_handler_creates_approval_and_waits(self) -> None:
        mock_record = MagicMock()
        mock_record.id = "approval-123"

        with patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            handler = build_mcp_elicitation_handler(agent_id="agent-1", chat_id="chat-1")

            async def _resolve_after_delay() -> None:
                await asyncio.sleep(0.05)
                resolve_pending_elicitation("approval-123", "approve")

            task = asyncio.create_task(_resolve_after_delay())
            result = await asyncio.wait_for(
                handler("test-server", "Please confirm", {"type": "object"}),
                timeout=5.0,
            )
            await task

            assert result == "accept"
            assert "approval-123" not in _pending_elicitations

    @pytest.mark.asyncio
    async def test_handler_timeout_returns_cancel(self) -> None:
        mock_record = MagicMock()
        mock_record.id = "approval-timeout"

        with (
            patch(
                "app.services.approvals.registry.ApprovalRegistry.create_approval",
                new_callable=AsyncMock,
                return_value=mock_record,
            ),
            patch(
                "app.services.agent.backends.mcp_elicitation_handler._ELICITATION_TIMEOUT_SECONDS",
                0.05,
            ),
        ):
            handler = build_mcp_elicitation_handler(agent_id="agent-1")
            result = await handler("srv", "Will timeout", {})

            assert result == "cancel"
            assert "approval-timeout" not in _pending_elicitations

    @pytest.mark.asyncio
    async def test_handler_deny_decision(self) -> None:
        mock_record = MagicMock()
        mock_record.id = "approval-deny"

        with patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            handler = build_mcp_elicitation_handler(agent_id="agent-1")

            async def _resolve_deny() -> None:
                await asyncio.sleep(0.05)
                resolve_pending_elicitation("approval-deny", "deny")

            task = asyncio.create_task(_resolve_deny())
            result = await asyncio.wait_for(
                handler("srv", "Deny test", {}),
                timeout=5.0,
            )
            await task

            assert result == "decline"

    @pytest.mark.asyncio
    async def test_handler_cleanup_on_completion(self) -> None:
        mock_record = MagicMock()
        mock_record.id = "approval-cleanup"

        with patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            handler = build_mcp_elicitation_handler(agent_id="agent-1")

            async def _resolve() -> None:
                await asyncio.sleep(0.05)
                resolve_pending_elicitation("approval-cleanup", "approve")

            task = asyncio.create_task(_resolve())
            await asyncio.wait_for(handler("srv", "Cleanup", {}), timeout=5.0)
            await task

            assert "approval-cleanup" not in _pending_elicitations

    @pytest.mark.asyncio
    async def test_handler_passes_correct_payload(self) -> None:
        mock_record = MagicMock()
        mock_record.id = "approval-payload"

        create_mock = AsyncMock(return_value=mock_record)
        with patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            create_mock,
        ):
            handler = build_mcp_elicitation_handler(
                agent_id="agent-42", chat_id="chat-7", thread_id="thread-3"
            )

            async def _resolve() -> None:
                await asyncio.sleep(0.05)
                resolve_pending_elicitation("approval-payload", "approve")

            task = asyncio.create_task(_resolve())
            await asyncio.wait_for(
                handler("github-mcp", "Deploy to prod?", {"properties": {"env": {"type": "string"}}}),
                timeout=5.0,
            )
            await task

            create_mock.assert_awaited_once()
            call_kwargs = create_mock.call_args[1]
            assert call_kwargs["agent_id"] == "agent-42"
            assert call_kwargs["chat_id"] == "chat-7"
            assert call_kwargs["thread_id"] == "thread-3"
            assert call_kwargs["action_type"] == "mcp_elicitation"
            assert call_kwargs["reason"] == "Deploy to prod?"
            payload = call_kwargs["payload"]
            assert payload["server_name"] == "github-mcp"
            assert payload["message"] == "Deploy to prod?"
            assert payload["action_type"] == "mcp_elicitation"
