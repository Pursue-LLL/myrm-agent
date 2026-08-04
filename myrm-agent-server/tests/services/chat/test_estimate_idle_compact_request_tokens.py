"""Tests for idle gate request-level token estimation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import Chat
from app.services.chat.compact_service import CompactResult, estimate_idle_compact_request_tokens
from app.services.chat.stale_compact_gate import maybe_compact_stale_chat_before_turn


@pytest.mark.asyncio
async def test_estimate_idle_compact_request_tokens_includes_compacted_summary() -> None:
    summary_text = '{"user_goal":"resume auth refactor","completed_actions":["setup"]}'
    db = AsyncMock()
    chat = Chat(id="chat-summary", compacted_summary=summary_text)

    with (
        patch(
            "app.services.chat.compact.idle_estimate.estimate_compactable_context_tokens",
            AsyncMock(return_value=(4_000, 8)),
        ),
        patch(
            "app.services.chat.compact.idle_estimate.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.idle_estimate.estimate_idle_compact_request_overhead",
            AsyncMock(return_value=8_000),
        ),
        patch(
            "app.services.chat.compact.idle_estimate.get_token_count",
            side_effect=lambda text: len(text) // 4,
        ),
    ):
        tokens, message_count = await estimate_idle_compact_request_tokens(
            db,
            "chat-summary",
            agent_id="agent-1",
        )

    summary_tokens = len(summary_text) // 4
    assert message_count == 8
    assert tokens == 4_000 + summary_tokens + 8_000


@pytest.mark.asyncio
async def test_estimate_idle_compact_request_tokens_without_summary() -> None:
    db = AsyncMock()
    chat = Chat(id="chat-plain", compacted_summary=None)

    with (
        patch(
            "app.services.chat.compact.idle_estimate.estimate_compactable_context_tokens",
            AsyncMock(return_value=(12_000, 15)),
        ),
        patch(
            "app.services.chat.compact.idle_estimate.load_chat",
            AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.chat.compact.idle_estimate.estimate_idle_compact_request_overhead",
            AsyncMock(return_value=8_000),
        ),
    ):
        tokens, message_count = await estimate_idle_compact_request_tokens(
            db,
            "chat-plain",
            agent_id=None,
        )

    assert message_count == 15
    assert tokens == 12_000 + 8_000


@pytest.mark.asyncio
async def test_gate_compacts_when_summary_pushes_tokens_above_floor() -> None:
    """Regression: tail-only estimate would skip; summary-inclusive estimate must compact."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )
    compact_result = CompactResult(compacted=True, tokens_saved=800, message_count=12)

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
            AsyncMock(return_value=(45_000, 12)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.resolve_idle_compact_token_floor",
            return_value=12_800,
        ),
        patch(
            "app.services.chat.stale_compact_gate.compact_chat",
            AsyncMock(return_value=compact_result),
        ) as mock_compact,
    ):
        result = await maybe_compact_stale_chat_before_turn(
            db,
            "chat-1",
            idle_after_seconds=1800,
            max_context_tokens=128_000,
        )

    assert result.compacted is True
    mock_compact.assert_awaited_once_with(
        db, "chat-1", for_idle_stale=True, request_tokens_for_guard=45_000
    )


@pytest.mark.asyncio
async def test_gate_compacts_incremental_tail_with_for_idle_stale_flag() -> None:
    """Idle gate compacts short tails when tokens>floor; compact_chat gets for_idle_stale."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )
    compact_result = CompactResult(compacted=True, tokens_saved=500, message_count=8)

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
            AsyncMock(return_value=(45_000, 8)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.resolve_idle_compact_token_floor",
            return_value=12_800,
        ),
        patch(
            "app.services.chat.stale_compact_gate.compact_chat",
            AsyncMock(return_value=compact_result),
        ) as mock_compact,
    ):
        result = await maybe_compact_stale_chat_before_turn(
            db,
            "chat-1",
            idle_after_seconds=1800,
            max_context_tokens=128_000,
        )

    assert result.compacted is True
    mock_compact.assert_awaited_once_with(
        db, "chat-1", for_idle_stale=True, request_tokens_for_guard=45_000
    )


def test_resolve_min_messages_to_compact_incremental() -> None:
    from app.services.chat.compact_service import resolve_min_messages_to_compact

    assert resolve_min_messages_to_compact(compacted_summary=None) == 10
    assert resolve_min_messages_to_compact(compacted_summary="") == 10
    assert resolve_min_messages_to_compact(compacted_summary='{"user_goal":"x"}') == 2


def _scalar_result(value: object) -> object:
    return type(
        "Row",
        (),
        {"scalar_one_or_none": lambda self: value},
    )()
