"""Tests for pre-reply stale compact gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.compact_service import CompactResult
from app.services.chat.stale_compact_gate import (
    maybe_compact_stale_chat_before_turn,
    parse_idle_compact_after_seconds,
    resolve_idle_compact_after_seconds,
    run_pre_reply_stale_compact_gate,
)


def test_parse_idle_compact_after_seconds_defaults_to_zero() -> None:
    assert parse_idle_compact_after_seconds(None) == 0
    assert parse_idle_compact_after_seconds({}) == 0
    assert parse_idle_compact_after_seconds({"idle_compact_after_seconds": 1800}) == 1800
    assert parse_idle_compact_after_seconds({"idle_compact_after_seconds": -5}) == 0
    assert parse_idle_compact_after_seconds({"idle_compact_after_seconds": "bad"}) == 0


@pytest.mark.asyncio
async def test_resolve_idle_compact_after_seconds_merges_request_override() -> None:
    mock_profile = AsyncMock()
    mock_profile.engine_params = {"idle_compact_after_seconds": 900}
    with patch(
        "app.services.agent.profile_resolver.get_agent_profile_resolver",
    ) as mock_get_resolver:
        mock_get_resolver.return_value.resolve = AsyncMock(return_value=mock_profile)
        seconds = await resolve_idle_compact_after_seconds(
            "agent-1",
            {"idle_compact_after_seconds": 1800},
        )
    assert seconds == 1800


@pytest.mark.asyncio
async def test_gate_skips_when_disabled() -> None:
    result = await maybe_compact_stale_chat_before_turn(
        AsyncMock(),
        "chat-1",
        idle_after_seconds=0,
    )
    assert result.compacted is False
    assert result.reason == "idle_compact_disabled"


@pytest.mark.asyncio
async def test_gate_compacts_when_idle_threshold_and_tokens_above_floor() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(None),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )
    compact_result = CompactResult(compacted=True, tokens_saved=1200, message_count=12)

    with (
        patch(
            "app.services.chat.stale_compact_gate.estimate_compactable_context_tokens",
            AsyncMock(return_value=(50_000, 20)),
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
        )

    assert result.compacted is True
    assert result.tokens_saved == 1200
    mock_compact.assert_awaited_once()


@pytest.mark.asyncio
async def test_gate_skips_when_context_below_floor() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(None),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.estimate_compactable_context_tokens",
            AsyncMock(return_value=(2_000, 12)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.resolve_idle_compact_token_floor",
            return_value=12_800,
        ),
        patch(
            "app.services.chat.stale_compact_gate.compact_chat",
            AsyncMock(),
        ) as mock_compact,
    ):
        result = await maybe_compact_stale_chat_before_turn(
            db,
            "chat-1",
            idle_after_seconds=1800,
        )

    assert result.compacted is False
    assert result.reason is not None
    assert "context_below_floor" in result.reason
    mock_compact.assert_not_called()


@pytest.mark.asyncio
async def test_gate_skips_large_window_small_context_via_model_floor() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(None),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.estimate_compactable_context_tokens",
            AsyncMock(return_value=(40_000, 20)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.compact_chat",
            AsyncMock(),
        ) as mock_compact,
    ):
        result = await maybe_compact_stale_chat_before_turn(
            db,
            "chat-1",
            idle_after_seconds=1800,
            max_context_tokens=1_000_000,
        )

    assert result.compacted is False
    assert result.reason is not None
    assert "context_below_floor" in result.reason
    mock_compact.assert_not_called()


@pytest.mark.asyncio
async def test_gate_skips_when_too_few_messages() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(None),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.estimate_compactable_context_tokens",
            AsyncMock(return_value=(500, 3)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.compact_chat",
            AsyncMock(),
        ) as mock_compact,
    ):
        result = await maybe_compact_stale_chat_before_turn(
            db,
            "chat-1",
            idle_after_seconds=1800,
        )

    assert result.compacted is False
    assert result.reason is not None
    assert "too_few_messages" in result.reason
    mock_compact.assert_not_called()


@pytest.mark.asyncio
async def test_run_pre_reply_stale_compact_gate_delegates_with_profile() -> None:
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)
    gate_result = CompactResult(compacted=False, reason="idle_below_threshold")

    with (
        patch(
            "app.services.chat.stale_compact_gate.resolve_idle_compact_after_seconds",
            AsyncMock(return_value=1800),
        ),
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.chat.stale_compact_gate.maybe_compact_stale_chat_before_turn",
            AsyncMock(return_value=gate_result),
        ) as mock_gate,
    ):
        result = await run_pre_reply_stale_compact_gate(
            "chat-1",
            agent_id="agent-1",
            request_engine_params={"idle_compact_after_seconds": 3600},
        )

    assert result is gate_result
    mock_gate.assert_awaited_once()
    assert mock_gate.await_args.kwargs["idle_after_seconds"] == 1800


def _scalar_result(value: object) -> object:
    return type(
        "Row",
        (),
        {"scalar_one_or_none": lambda self: value},
    )()
