"""Tests for pre-reply stale compact gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.compact_service import CompactResult
from app.services.chat.stale_compact_gate import (
    ModelWindowUnavailableError,
    maybe_compact_stale_chat_before_turn,
    parse_idle_compact_after_seconds,
    resolve_idle_compact_after_seconds,
    run_pre_reply_stale_compact_gate,
)


def test_parse_idle_compact_after_seconds_defaults_to_zero() -> None:
    assert parse_idle_compact_after_seconds(None) == 0
    assert parse_idle_compact_after_seconds({}) == 0
    assert (
        parse_idle_compact_after_seconds({"idle_compact_after_seconds": 1800}) == 1800
    )
    assert parse_idle_compact_after_seconds({"idle_compact_after_seconds": -5}) == 0
    assert parse_idle_compact_after_seconds({"idle_compact_after_seconds": "bad"}) == 0


@pytest.mark.asyncio
async def test_resolve_idle_compact_after_seconds_merges_request_override() -> None:
    mock_profile = AsyncMock()
    mock_profile.engine_params = {"idle_compact_after_seconds": 900}
    with patch(
        "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
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
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )
    compact_result = CompactResult(compacted=True, tokens_saved=1200, message_count=12)

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
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
            max_context_tokens=128_000,
        )

    assert result.compacted is True
    assert result.tokens_saved == 1200
    assert result.attempted is True
    mock_compact.assert_awaited_once_with(
        db, "chat-1", for_idle_stale=True, request_tokens_for_guard=50_000
    )


@pytest.mark.asyncio
async def test_gate_skips_when_context_below_floor() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
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
            max_context_tokens=128_000,
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
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
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
async def test_gate_compacts_when_eight_messages_above_floor() -> None:
    """Idle gate uses Hermes predicate (tokens>floor); no min message count."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )
    compact_result = CompactResult(compacted=True, tokens_saved=800, message_count=8)

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
    assert result.message_count == 8
    mock_compact.assert_awaited_once_with(
        db, "chat-1", for_idle_stale=True, request_tokens_for_guard=45_000
    )


@pytest.mark.asyncio
async def test_gate_skips_when_context_below_floor_despite_few_messages() -> None:
    """Few messages but tokens below floor still skip (Hermes floor semantics)."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
            AsyncMock(return_value=(500, 3)),
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
            max_context_tokens=128_000,
        )

    assert result.compacted is False
    assert result.reason is not None
    assert "context_below_floor" in result.reason
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


@pytest.mark.asyncio
async def test_gate_skips_when_model_window_unavailable_fail_closed() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
            AsyncMock(return_value=(100_000, 20)),
        ),
        patch(
            "app.services.chat.stale_compact_gate._resolve_max_context_tokens",
            AsyncMock(side_effect=ModelWindowUnavailableError("config incomplete")),
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
    assert result.reason == "model_window_unavailable_fail_closed"
    mock_compact.assert_not_called()


@pytest.mark.asyncio
async def test_gate_skips_when_model_window_resolves_to_none_fail_closed() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
            AsyncMock(return_value=(100_000, 20)),
        ),
        patch(
            "app.services.chat.stale_compact_gate._resolve_max_context_tokens",
            AsyncMock(return_value=None),
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
    assert result.reason == "model_window_unavailable_fail_closed"
    mock_compact.assert_not_called()


@pytest.mark.asyncio
async def test_gate_skips_when_compaction_failure_cooldown_active() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(True, "timeout: summarize failed")),
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
            max_context_tokens=128_000,
        )

    assert result.compacted is False
    assert result.reason is not None
    assert "compression_failure_cooldown_active" in result.reason
    mock_compact.assert_not_called()


@pytest.mark.asyncio
async def test_gate_skips_when_no_compactable_messages_despite_summary_overhead() -> (
    None
):
    """Summary+overhead can exceed floor while compactable tail is empty."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result("chat-1"),
            _scalar_result(datetime.now(UTC) - timedelta(hours=2)),
        ]
    )
    compact_result = CompactResult(
        compacted=False, message_count=0, reason="no_compactable_messages"
    )

    with (
        patch(
            "app.services.chat.stale_compact_gate.is_compaction_failure_cooldown_active",
            AsyncMock(return_value=(False, None)),
        ),
        patch(
            "app.services.chat.stale_compact_gate.estimate_idle_compact_request_tokens",
            AsyncMock(return_value=(45_000, 0)),
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

    assert result.compacted is False
    assert result.reason == "no_compactable_messages"
    assert result.attempted is True
    mock_compact.assert_awaited_once_with(
        db, "chat-1", for_idle_stale=True, request_tokens_for_guard=45_000
    )


def _scalar_result(value: object) -> object:
    return type(
        "Row",
        (),
        {"scalar_one_or_none": lambda self: value},
    )()
