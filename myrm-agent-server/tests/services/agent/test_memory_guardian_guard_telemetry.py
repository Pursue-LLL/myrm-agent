"""Tests for memory guardian guard-unavailable telemetry dispatcher."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import app.services.agent.memory_guardian_guard_telemetry as telemetry
import app.services.agent.memory_guardian_guard_telemetry.dispatcher as telemetry_dispatcher
from app.config.settings import (
    ControlPlaneSettings,
    MemoryGuardianGuardTelemetrySettings,
    settings,
)
from app.schemas.control_plane import MemoryGuardianGuardBatchPayload
from app.services.agent.memory_guardian_guard_telemetry import (
    MemoryGuardianGuardTelemetryConfig,
    MemoryGuardianGuardTelemetryDispatcher,
    MemoryGuardianGuardTelemetryEvent,
    enqueue_memory_guardian_guard_telemetry,
    start_memory_guardian_guard_telemetry_dispatcher,
    stop_memory_guardian_guard_telemetry_dispatcher,
)


def _patch_telemetry_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str = "",
    telemetry_token: str = "",
    telemetry_subject: str = "",
    batch_size: int = 24,
    flush_interval_seconds: float = 3.0,
    queue_size: int = 256,
) -> None:
    monkeypatch.setattr(
        settings,
        "control_plane",
        ControlPlaneSettings.model_validate(
            {
                "CONTROL_PLANE_URL": url,
                "CONTROL_PLANE_TELEMETRY_TOKEN": telemetry_token,
                "CONTROL_PLANE_TELEMETRY_SUBJECT": telemetry_subject,
            }
        ),
    )
    monkeypatch.setattr(
        settings,
        "memory_guardian_guard_telemetry",
        MemoryGuardianGuardTelemetrySettings(
            batch_size=batch_size,
            flush_interval_seconds=flush_interval_seconds,
            queue_size=queue_size,
        ),
    )


def test_partial_env_config_disables_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001",
        telemetry_token="",
        telemetry_subject="sandbox-42",
    )

    assert MemoryGuardianGuardTelemetryConfig.from_settings() is None


def test_invalid_numeric_settings_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001/",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=0,
        flush_interval_seconds=-1.0,
        queue_size=0,
    )

    config = MemoryGuardianGuardTelemetryConfig.from_settings()

    assert config is not None
    assert config.control_plane_url == "http://control-plane:8001"
    assert config.batch_size == 24
    assert config.flush_interval_seconds == 3.0
    assert config.queue_size == 256


@pytest.mark.asyncio
async def test_flush_batch_aggregates_events_before_post() -> None:
    config = MemoryGuardianGuardTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = MemoryGuardianGuardTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)

    batch = [
        MemoryGuardianGuardTelemetryEvent(
            reason="budget_guard_unavailable",
            guard="budget",
            frequency_tier="balanced",
            quiet_window_enabled=True,
        ),
        MemoryGuardianGuardTelemetryEvent(
            reason="budget_guard_unavailable",
            guard="budget",
            frequency_tier="balanced",
            quiet_window_enabled=True,
        ),
        MemoryGuardianGuardTelemetryEvent(
            reason="capacity_guard_unavailable",
            guard="capacity",
            frequency_tier="aggressive",
            quiet_window_enabled=False,
        ),
    ]

    await dispatcher._flush_batch(batch)

    assert dispatcher._client.post.await_count == 1
    first_call = dispatcher._client.post.await_args_list[0]
    payload = MemoryGuardianGuardBatchPayload.model_validate(first_call.kwargs["json"])
    assert first_call.kwargs["headers"]["X-Telemetry-Subject"] == "sandbox-42"
    aggregates = {
        (
            item.reason,
            item.guard,
            item.frequency_tier,
            item.quiet_window_enabled,
        ): item.count
        for item in payload.events[0].aggregates
    }
    assert aggregates == {
        ("budget_guard_unavailable", "budget", "balanced", True): 2,
        ("capacity_guard_unavailable", "capacity", "aggressive", False): 1,
    }


@pytest.mark.asyncio
async def test_dispatcher_helpers_manage_global_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        flush_interval_seconds=0.01,
    )
    monkeypatch.setattr(telemetry_dispatcher, "_dispatcher", None)
    monkeypatch.setattr(
        telemetry_dispatcher.MemoryGuardianGuardTelemetryDispatcher,
        "_flush_batch",
        AsyncMock(return_value=None),
    )

    try:
        await start_memory_guardian_guard_telemetry_dispatcher()
        assert telemetry_dispatcher._dispatcher is not None

        enqueue_memory_guardian_guard_telemetry(
            reason=" budget_guard_unavailable ",
            guard=" budget ",
            frequency_tier="balanced",
            quiet_window_enabled=True,
        )
        await asyncio.sleep(0)

        await stop_memory_guardian_guard_telemetry_dispatcher()
        assert telemetry_dispatcher._dispatcher is None
    finally:
        monkeypatch.setattr(telemetry_dispatcher, "_dispatcher", None)


@pytest.mark.asyncio
async def test_queue_full_coalesces_dropped_event_into_next_flush() -> None:
    config = MemoryGuardianGuardTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=1,
    )
    dispatcher = MemoryGuardianGuardTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)

    first_event = MemoryGuardianGuardTelemetryEvent(
        reason="budget_guard_unavailable",
        guard="budget",
        frequency_tier="balanced",
        quiet_window_enabled=True,
    )
    second_event = MemoryGuardianGuardTelemetryEvent(
        reason="capacity_guard_unavailable",
        guard="capacity",
        frequency_tier="aggressive",
        quiet_window_enabled=False,
    )
    dispatcher.enqueue(first_event)
    dispatcher.enqueue(second_event)

    queued_event = dispatcher._pop_next_event()
    assert queued_event == second_event

    await dispatcher._flush_batch([second_event])

    assert dispatcher._client.post.await_count == 1
    payload = MemoryGuardianGuardBatchPayload.model_validate(dispatcher._client.post.await_args.kwargs["json"])
    aggregate_counts = {
        (aggregate.reason, aggregate.guard, aggregate.frequency_tier, aggregate.quiet_window_enabled): aggregate.count
        for aggregate in payload.events[0].aggregates
    }
    assert aggregate_counts == {
        ("budget_guard_unavailable", "budget", "balanced", True): 1,
        ("capacity_guard_unavailable", "capacity", "aggressive", False): 1,
    }


@pytest.mark.asyncio
async def test_flush_failure_preserves_aggregates_for_retry() -> None:
    config = MemoryGuardianGuardTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = MemoryGuardianGuardTelemetryDispatcher(config)
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(
        side_effect=[httpx.ConnectError("offline"), httpx.ConnectError("offline")]
    )

    event = MemoryGuardianGuardTelemetryEvent(
        reason="budget_guard_unavailable",
        guard="budget",
        frequency_tier="balanced",
        quiet_window_enabled=True,
    )
    await dispatcher._flush_batch([event])

    assert len(dispatcher._pending_envelopes) == 1
    pending_aggregate = dispatcher._pending_envelopes[0].aggregates[0]
    assert pending_aggregate.reason == "budget_guard_unavailable"
    assert pending_aggregate.count == 1

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)
    await dispatcher._flush_batch([])

    payload = MemoryGuardianGuardBatchPayload.model_validate(dispatcher._client.post.await_args.kwargs["json"])
    assert payload.events[0].aggregates[0].reason == "budget_guard_unavailable"
    assert payload.events[0].aggregates[0].count == 1
    assert len(dispatcher._pending_envelopes) == 0


@pytest.mark.asyncio
async def test_shutdown_does_not_loop_forever_when_final_flush_fails() -> None:
    config = MemoryGuardianGuardTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = MemoryGuardianGuardTelemetryDispatcher(config)
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(
        side_effect=[httpx.ConnectError("offline"), httpx.ConnectError("offline")]
    )
    dispatcher._merge_aggregates(
        {
            MemoryGuardianGuardTelemetryEvent(
                reason="budget_guard_unavailable",
                guard="budget",
                frequency_tier="balanced",
                quiet_window_enabled=True,
            ): 1
        }
    )
    dispatcher._stop_event.set()

    worker_task = asyncio.create_task(dispatcher._run())
    await asyncio.wait_for(worker_task, timeout=1.0)

    assert worker_task.done()

