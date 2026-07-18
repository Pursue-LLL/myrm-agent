"""Tests for memory brief status telemetry dispatcher with phase labels."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import app.services.agent.memory_brief_status_telemetry as telemetry
from app.config.settings import (
    ControlPlaneSettings,
    MemoryBriefStatusTelemetrySettings,
    settings,
)
from app.schemas.control_plane import MemoryBriefStatusBatchPayload
from app.services.agent.memory_brief_status_telemetry import (
    MemoryBriefStatusTelemetryConfig,
    MemoryBriefStatusTelemetryDispatcher,
    MemoryBriefStatusTelemetryEvent,
    _build_memory_brief_status_event,
    enqueue_memory_brief_status_telemetry,
    start_memory_brief_status_telemetry_dispatcher,
    stop_memory_brief_status_telemetry_dispatcher,
)


class _DummyCounter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def labels(self, **labels: str) -> _DummyCounter:
        self.calls.append(labels)
        return self

    def inc(self) -> None:
        return None


def _patch_telemetry_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str = "",
    telemetry_token: str = "",
    telemetry_subject: str = "",
    batch_size: int = 32,
    flush_interval_seconds: float = 3.0,
    queue_size: int = 512,
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
        "memory_brief_status_telemetry",
        MemoryBriefStatusTelemetrySettings(
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

    assert MemoryBriefStatusTelemetryConfig.from_settings() is None


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

    config = MemoryBriefStatusTelemetryConfig.from_settings()

    assert config is not None
    assert config.control_plane_url == "http://control-plane:8001"
    assert config.batch_size == 32
    assert config.flush_interval_seconds == 3.0
    assert config.queue_size == 512


def test_build_event_normalizes_phase_and_labels() -> None:
    payload = {
        "state": "skipped",
        "source": "runtime_fallback",
        "injection": {
            "state": "not_applied",
            "reason": "missing_context",
        },
    }
    event = _build_memory_brief_status_event("stream", payload)

    assert event == MemoryBriefStatusTelemetryEvent(
        phase="stream",
        brief_state="skipped",
        brief_reason="none",
        brief_source="runtime_fallback",
        injection_state="not_applied",
        injection_source="none",
        injection_reason="missing_context",
    )
    assert _build_memory_brief_status_event("", payload) is None
    assert _build_memory_brief_status_event("stream", {"source": "preflight"}) is None


def test_enqueue_drops_oldest_event_when_queue_full(caplog: pytest.LogCaptureFixture) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=1,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    payload = {"state": "ready"}
    dropped_counter = _DummyCounter()
    previous_counter = telemetry._MEMORY_STATUS_DROPPED
    telemetry._MEMORY_STATUS_DROPPED = dropped_counter

    try:
        with caplog.at_level(logging.WARNING):
            dispatcher.enqueue("stream", payload)
            dispatcher.enqueue("persist", payload)

        retained = dispatcher._queue.get_nowait()
        assert retained.phase == "persist"
        assert retained.brief_state == "ready"
        assert "dropping oldest event phase=stream" in caplog.text
        assert dropped_counter.calls == [
            {
                "dropped_phase": "stream",
                "incoming_phase": "persist",
            }
        ]
    finally:
        telemetry._MEMORY_STATUS_DROPPED = previous_counter


@pytest.mark.asyncio
async def test_dispatcher_batches_multiple_events() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)

    dispatcher._flush_batch = AsyncMock()
    await dispatcher.start()
    dispatcher.enqueue("stream", {"state": "ready"})
    dispatcher.enqueue("persist", {"state": "skipped", "source": "preflight"})
    await asyncio.sleep(0.05)
    await dispatcher.stop()

    dispatcher._flush_batch.assert_called()
    flushed_batch = dispatcher._flush_batch.await_args_list[0].args[0]
    assert len(flushed_batch) == 2
    assert [item.phase for item in flushed_batch] == ["stream", "persist"]
    assert [item.brief_state for item in flushed_batch] == ["ready", "skipped"]


@pytest.mark.asyncio
async def test_flush_batch_aggregates_events_before_post() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)

    batch = [
        MemoryBriefStatusTelemetryEvent(
            phase="stream",
            brief_state="skipped",
            brief_reason="none",
            brief_source="runtime_fallback",
            injection_state="not_applied",
            injection_source="none",
            injection_reason="missing_context",
        ),
        MemoryBriefStatusTelemetryEvent(
            phase="stream",
            brief_state="skipped",
            brief_reason="none",
            brief_source="runtime_fallback",
            injection_state="not_applied",
            injection_source="none",
            injection_reason="missing_context",
        ),
        MemoryBriefStatusTelemetryEvent(
            phase="persist",
            brief_state="skipped",
            brief_reason="timeout",
            brief_source="preflight",
            injection_state="applied",
            injection_source="snapshot",
            injection_reason="none",
        ),
    ]

    await dispatcher._flush_batch(batch)

    assert dispatcher._client.post.await_count == 1
    first_call = dispatcher._client.post.await_args_list[0]
    payload = MemoryBriefStatusBatchPayload.model_validate(first_call.kwargs["json"])
    assert first_call.kwargs["headers"]["X-Telemetry-Subject"] == "sandbox-42"
    aggregates = {
        (
            item.phase,
            item.brief_state,
            item.brief_source,
            item.injection_state,
            item.injection_reason,
        ): item.count
        for item in payload.events[0].aggregates
    }
    assert aggregates == {
        ("stream", "skipped", "runtime_fallback", "not_applied", "missing_context"): 2,
        ("persist", "skipped", "preflight", "applied", "none"): 1,
    }


@pytest.mark.asyncio
async def test_flush_batch_retries_then_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
        ]
    )
    batch = [
        MemoryBriefStatusTelemetryEvent(
            phase="stream",
            brief_state="ready",
            brief_reason="none",
            brief_source="preflight",
            injection_state="none",
            injection_source="none",
            injection_reason="none",
        )
    ]

    with caplog.at_level(logging.WARNING):
        await dispatcher._flush_batch(batch)

    assert dispatcher._client.post.await_count == 2
    assert "Failed to flush 1 memory brief status telemetry events" in caplog.text


@pytest.mark.asyncio
async def test_dispatcher_helpers_manage_global_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        flush_interval_seconds=0.01,
    )
    monkeypatch.setattr(telemetry, "_dispatcher", None)

    try:
        await start_memory_brief_status_telemetry_dispatcher()
        assert telemetry._dispatcher is not None

        enqueue_memory_brief_status_telemetry(
            phase="stream",
            payload={"state": "ready"},
        )

        await stop_memory_brief_status_telemetry_dispatcher()
        assert telemetry._dispatcher is None
    finally:
        monkeypatch.setattr(telemetry, "_dispatcher", None)


def test_enqueue_helper_passes_phase_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatcher = MagicMock()
    monkeypatch.setattr(telemetry, "_dispatcher", dispatcher)

    enqueue_memory_brief_status_telemetry(
        phase="stream",
        payload={"state": "ready"},
    )

    dispatcher.enqueue.assert_called_once_with("stream", {"state": "ready"})
