"""Tests for memory brief status telemetry dispatcher with phase labels."""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import ValidationError

import app.services.agent.memory_brief_telemetry.dispatcher as telemetry_dispatcher
import app.services.agent.memory_brief_telemetry.dropped_store as dropped_store_module
import app.services.agent.memory_brief_telemetry.metrics as telemetry_metrics
from app.config.settings import (
    ControlPlaneSettings,
    MemoryBriefStatusTelemetrySettings,
    settings,
)
from app.schemas.control_plane import MemoryBriefStatusBatchPayload
from app.services.agent.memory_brief_telemetry import (
    MemoryBriefStatusTelemetryConfig,
    MemoryBriefStatusTelemetryDispatcher,
    MemoryBriefStatusTelemetryEvent,
    build_memory_brief_status_event,
    enqueue_memory_brief_status_telemetry,
    start_memory_brief_status_telemetry_dispatcher,
    stop_memory_brief_status_telemetry_dispatcher,
)

_ALLOWED_PHASES = frozenset({"stream", "persist"})


def test_memory_brief_batch_payload_rejects_too_long_envelope_id() -> None:
    payload = {
        "events": [
            {
                "telemetry_subject": "sandbox-42",
                "envelope_id": "x" * 129,
                "timestamp": "2026-05-19T00:00:00+00:00",
                "aggregates": [
                    {
                        "phase": "stream",
                        "brief_state": "ready",
                        "brief_reason": "none",
                        "brief_source": "preflight",
                        "injection_state": "applied",
                        "injection_source": "snapshot",
                        "injection_reason": "none",
                        "count": 1,
                    }
                ],
                "dropped_aggregates": [],
            }
        ]
    }

    with pytest.raises(ValidationError):
        MemoryBriefStatusBatchPayload.model_validate(payload)


class _DummyCounter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.inc_count = 0

    def labels(self, **labels: str) -> _DummyCounter:
        self.calls.append(labels)
        return self

    def inc(self) -> None:
        self.inc_count += 1


def _patch_telemetry_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str = "",
    telemetry_token: str = "",
    telemetry_subject: str = "",
    batch_size: int = 32,
    flush_interval_seconds: float = 3.0,
    queue_size: int = 512,
    allowed_phases: str = "stream,persist",
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
            allowed_phases=allowed_phases,
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
    assert config.allowed_phases == _ALLOWED_PHASES
    assert config.dropped_state_path.endswith("memory_brief_status_dropped_aggregates.json")


def test_empty_allowed_phases_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001/",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        allowed_phases=",,",
    )

    config = MemoryBriefStatusTelemetryConfig.from_settings()

    assert config is not None
    assert config.allowed_phases == _ALLOWED_PHASES


def test_allowed_phases_filters_unsupported_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001/",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        allowed_phases="stream,worker,persist",
    )

    config = MemoryBriefStatusTelemetryConfig.from_settings()

    assert config is not None
    assert config.allowed_phases == _ALLOWED_PHASES


def test_allowed_phases_fall_back_when_only_unsupported_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001/",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        allowed_phases="worker",
    )

    config = MemoryBriefStatusTelemetryConfig.from_settings()

    assert config is not None
    assert config.allowed_phases == _ALLOWED_PHASES


def test_build_event_normalizes_phase_and_labels() -> None:
    payload = {
        "state": "skipped",
        "source": "runtime_fallback",
        "injection": {
            "state": "not_applied",
            "reason": "missing_context",
        },
    }
    event = build_memory_brief_status_event("stream", payload)

    assert event == MemoryBriefStatusTelemetryEvent(
        phase="stream",
        brief_state="skipped",
        brief_reason="none",
        brief_source="runtime_fallback",
        injection_state="not_applied",
        injection_source="none",
        injection_reason="missing_context",
    )
    assert build_memory_brief_status_event("", payload) is None
    assert build_memory_brief_status_event("worker", payload) is None
    assert build_memory_brief_status_event("stream", {"source": "preflight"}) is None


def test_enqueue_drops_oldest_event_when_queue_full(caplog: pytest.LogCaptureFixture) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=1,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    payload = {"state": "ready"}
    dropped_counter = _DummyCounter()
    previous_counter = telemetry_metrics.MEMORY_STATUS_DROPPED
    telemetry_metrics.MEMORY_STATUS_DROPPED = dropped_counter

    try:
        with caplog.at_level(logging.WARNING):
            dispatcher.enqueue("stream", payload)
            dispatcher.enqueue("persist", payload)

        assert dispatcher._queued_persist_count == 1
        assert dispatcher._queued_stream_count == 0
        assert "dropping queued event phase=stream" in caplog.text
        assert dropped_counter.calls == [
            {
                "telemetry_subject": "sandbox-42",
                "dropped_phase": "stream",
                "incoming_phase": "persist",
            }
        ]
    finally:
        telemetry_metrics.MEMORY_STATUS_DROPPED = previous_counter


def test_enqueue_drops_incoming_stream_when_persist_already_buffered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=1,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    payload = {"state": "ready"}
    dropped_counter = _DummyCounter()
    previous_counter = telemetry_metrics.MEMORY_STATUS_DROPPED
    telemetry_metrics.MEMORY_STATUS_DROPPED = dropped_counter

    try:
        with caplog.at_level(logging.WARNING):
            dispatcher.enqueue("persist", payload)
            dispatcher.enqueue("stream", payload)

        assert dispatcher._queued_persist_count == 1
        assert dispatcher._queued_stream_count == 0
        assert "dropping incoming stream event to preserve persist event" in caplog.text
        assert dropped_counter.calls == [
            {
                "telemetry_subject": "sandbox-42",
                "dropped_phase": "stream",
                "incoming_phase": "stream",
            }
        ]
    finally:
        telemetry_metrics.MEMORY_STATUS_DROPPED = previous_counter


def test_enqueue_persist_prefers_dropping_queued_stream_over_persist() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=2,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    payload = {"state": "ready"}
    dropped_counter = _DummyCounter()
    previous_counter = telemetry_metrics.MEMORY_STATUS_DROPPED
    telemetry_metrics.MEMORY_STATUS_DROPPED = dropped_counter

    try:
        dispatcher.enqueue("persist", payload)
        dispatcher.enqueue("stream", payload)
        dispatcher.enqueue("persist", payload)

        assert dispatcher._queued_persist_count == 2
        assert dispatcher._queued_stream_count == 0
        assert dropped_counter.calls == [
            {
                "telemetry_subject": "sandbox-42",
                "dropped_phase": "stream",
                "incoming_phase": "persist",
            }
        ]
    finally:
        telemetry_metrics.MEMORY_STATUS_DROPPED = previous_counter


@pytest.mark.asyncio
async def test_dispatcher_batches_multiple_events() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
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
    assert {item.phase for item in flushed_batch} == {"stream", "persist"}
    assert {item.brief_state for item in flushed_batch} == {"ready", "skipped"}


@pytest.mark.asyncio
async def test_dispatcher_run_survives_unexpected_flush_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    flush_ex_counter = _DummyCounter()
    previous_flush_counter = telemetry_metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS
    telemetry_metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS = flush_ex_counter

    async def _raise_unexpected(_: list[MemoryBriefStatusTelemetryEvent]) -> None:
        raise RuntimeError("unexpected serializer failure")

    dispatcher._flush_batch = AsyncMock(side_effect=_raise_unexpected)

    try:
        with caplog.at_level(logging.WARNING):
            await dispatcher.start()
            dispatcher.enqueue("stream", {"state": "ready"})
            await asyncio.sleep(0.05)
            await dispatcher.stop()
    finally:
        telemetry_metrics.MEMORY_STATUS_FLUSH_EXCEPTIONS = previous_flush_counter

    assert "Memory brief status telemetry flush loop crashed on unexpected error" in caplog.text
    assert flush_ex_counter.calls == [{"telemetry_subject": "sandbox-42"}]
    assert flush_ex_counter.inc_count == 1


@pytest.mark.asyncio
async def test_flush_batch_aggregates_events_before_post() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
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
    assert payload.events[0].envelope_id.startswith("mbs-")
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
    assert payload.events[0].dropped_aggregates == []


@pytest.mark.asyncio
async def test_flush_batch_includes_pending_dropped_aggregates() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)

    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    batch = [
        MemoryBriefStatusTelemetryEvent(
            phase="persist",
            brief_state="ready",
            brief_reason="none",
            brief_source="preflight",
            injection_state="none",
            injection_source="none",
            injection_reason="none",
        )
    ]

    await dispatcher._flush_batch(batch)
    call = dispatcher._client.post.await_args_list[0]
    payload = MemoryBriefStatusBatchPayload.model_validate(call.kwargs["json"])
    assert payload.events[0].envelope_id.startswith("mbs-")
    assert [row.model_dump() for row in payload.events[0].dropped_aggregates] == [
        {"dropped_phase": "stream", "incoming_phase": "persist", "count": 1}
    ]
    assert dispatcher._dropped_store.counts == {}


@pytest.mark.asyncio
async def test_flush_batch_keeps_dropped_aggregates_when_post_fails() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=8,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
        ]
    )
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
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

    await dispatcher._flush_batch(batch)

    assert dispatcher._dropped_store.counts == {("stream", "persist"): 1}


@pytest.mark.asyncio
async def test_flush_batch_retries_then_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
        ]
    )
    flush_http_error_counter = _DummyCounter()
    flush_attempt_counter = _DummyCounter()
    previous_http_error_counter = telemetry_metrics.MEMORY_STATUS_FLUSH_HTTP_ERRORS
    previous_attempt_counter = telemetry_metrics.MEMORY_STATUS_FLUSH_ATTEMPTS
    telemetry_metrics.MEMORY_STATUS_FLUSH_HTTP_ERRORS = flush_http_error_counter
    telemetry_metrics.MEMORY_STATUS_FLUSH_ATTEMPTS = flush_attempt_counter
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

    try:
        with caplog.at_level(logging.WARNING):
            await dispatcher._flush_batch(batch)
    finally:
        telemetry_metrics.MEMORY_STATUS_FLUSH_HTTP_ERRORS = previous_http_error_counter
        telemetry_metrics.MEMORY_STATUS_FLUSH_ATTEMPTS = previous_attempt_counter

    assert dispatcher._client.post.await_count == 2
    assert (
        "Failed to flush memory brief status telemetry to http://control-plane:8001/api/telemetry/memory-brief-status/batch"
        in caplog.text
    )
    assert flush_http_error_counter.calls == [{"telemetry_subject": "sandbox-42"}]
    assert flush_http_error_counter.inc_count == 1
    assert flush_attempt_counter.calls == [
        {"telemetry_subject": "sandbox-42"},
        {"telemetry_subject": "sandbox-42"},
    ]
    assert flush_attempt_counter.inc_count == 2


@pytest.mark.asyncio
async def test_run_flushes_pending_dropped_aggregates_without_new_batch() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    worker = asyncio.create_task(dispatcher._run())
    await asyncio.sleep(0.05)
    dispatcher._stop_event.set()
    await worker

    assert dispatcher._client.post.await_count == 1
    payload = MemoryBriefStatusBatchPayload.model_validate(
        dispatcher._client.post.await_args_list[0].kwargs["json"]
    )
    assert payload.events[0].envelope_id.startswith("mbs-")
    assert payload.events[0].aggregates == []
    assert [row.model_dump() for row in payload.events[0].dropped_aggregates] == [
        {"dropped_phase": "stream", "incoming_phase": "persist", "count": 1}
    ]
    assert dispatcher._dropped_store.counts == {}


@pytest.mark.asyncio
async def test_run_recovers_persisted_dropped_aggregates_and_flushes_without_new_batch(
    tmp_path,
) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    dropped_state_path.write_text(
        json.dumps(
            {
                "dropped_aggregates": [
                    {"dropped_phase": "stream", "incoming_phase": "persist", "count": 2},
                    {"dropped_phase": "persist", "incoming_phase": "stream", "count": 1},
                ]
            }
        ),
        encoding="utf-8",
    )
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    dispatcher._client = MagicMock()
    dispatcher._client.post = AsyncMock(return_value=mock_response)

    worker = asyncio.create_task(dispatcher._run())
    await asyncio.sleep(0.05)
    dispatcher._stop_event.set()
    await worker

    assert dispatcher._client.post.await_count == 1
    payload = MemoryBriefStatusBatchPayload.model_validate(
        dispatcher._client.post.await_args_list[0].kwargs["json"]
    )
    assert payload.events[0].envelope_id.startswith("mbs-")
    assert payload.events[0].aggregates == []
    assert [row.model_dump() for row in payload.events[0].dropped_aggregates] == [
        {"dropped_phase": "persist", "incoming_phase": "stream", "count": 1},
        {"dropped_phase": "stream", "incoming_phase": "persist", "count": 2},
    ]
    assert dispatcher._dropped_store.counts == {}
    assert not dropped_state_path.exists()


def test_record_drop_persists_dropped_state_file(tmp_path) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    dispatcher._dropped_store.persist_if_needed(force=True)

    assert dropped_state_path.exists()
    payload = json.loads(dropped_state_path.read_text(encoding="utf-8"))
    assert payload == {
        "dropped_aggregates": [
            {"dropped_phase": "stream", "incoming_phase": "persist", "count": 2}
        ]
    }


def test_dropped_state_load_uses_inter_process_file_lock(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        def __init__(self) -> None:
            self.ops: list[int] = []

        def flock(self, _fd: int, op: int) -> None:
            self.ops.append(op)

    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    dropped_state_path.write_text(
        json.dumps(
            {
                "dropped_aggregates": [
                    {"dropped_phase": "stream", "incoming_phase": "persist", "count": 3}
                ]
            }
        ),
        encoding="utf-8",
    )
    fake_fcntl = _FakeFcntl()
    monkeypatch.setattr(dropped_store_module, "_fcntl", fake_fcntl)
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )

    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)

    assert dispatcher._dropped_store.counts == {("stream", "persist"): 3}
    assert fake_fcntl.ops.count(fake_fcntl.LOCK_EX) >= 1
    assert fake_fcntl.ops.count(fake_fcntl.LOCK_UN) >= 1


def test_dropped_state_persist_and_clear_use_inter_process_file_lock(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        def __init__(self) -> None:
            self.ops: list[int] = []

        def flock(self, _fd: int, op: int) -> None:
            self.ops.append(op)

    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    fake_fcntl = _FakeFcntl()
    monkeypatch.setattr(dropped_store_module, "_fcntl", fake_fcntl)
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    dispatcher._dropped_store.persist_if_needed(force=True)
    dispatcher._dropped_store.clear_persisted()

    lock_path = dropped_state_path.with_name(f"{dropped_state_path.name}.lock")
    assert lock_path.exists()
    assert fake_fcntl.ops.count(fake_fcntl.LOCK_EX) >= 2
    assert fake_fcntl.ops.count(fake_fcntl.LOCK_UN) >= 2


def test_record_drop_throttles_persist_writes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    persist_mock = MagicMock(return_value=True)
    monkeypatch.setattr(dispatcher._dropped_store, "persist_with_state", persist_mock)

    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")

    assert persist_mock.call_count == 1
    dispatcher._dropped_store.persist_if_needed(force=True)
    assert persist_mock.call_count == 2


def test_persist_failure_keeps_dropped_state_dirty_until_retry_succeeds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    persist_mock = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(dispatcher._dropped_store, "persist_with_state", persist_mock)

    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")

    assert persist_mock.call_count == 1
    assert dispatcher._dropped_store.dirty is True
    assert dispatcher._dropped_store.pending_updates > 0
    assert dispatcher._dropped_store.persist_failure_count == 1
    assert dispatcher._dropped_store.next_retry_monotonic > 0.0

    dispatcher._dropped_store.persist_if_needed(force=True)

    assert persist_mock.call_count == 2
    assert dispatcher._dropped_store.dirty is False
    assert dispatcher._dropped_store.pending_updates == 0
    assert dispatcher._dropped_store.persist_failure_count == 0
    assert dispatcher._dropped_store.next_retry_monotonic == 0.0


def test_persist_failure_backoff_blocks_non_forced_retry_until_window_expires(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    persist_mock = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(dispatcher._dropped_store, "persist_with_state", persist_mock)

    clock = {"now": 100.0}
    monkeypatch.setattr(dropped_store_module.time, "monotonic", lambda: clock["now"])

    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")

    assert persist_mock.call_count == 1
    retry_at = dispatcher._dropped_store.next_retry_monotonic
    assert retry_at > clock["now"]

    dispatcher._dropped_store.persist_if_needed()
    assert persist_mock.call_count == 1
    assert dispatcher._dropped_store.dirty is True

    clock["now"] = retry_at + 0.01
    dispatcher._dropped_store.persist_if_needed()

    assert persist_mock.call_count == 2
    assert dispatcher._dropped_store.dirty is False


def test_invalid_persisted_dropped_state_is_ignored_and_cleared(tmp_path) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    dropped_state_path.write_text('{"dropped_aggregates":"invalid"}', encoding="utf-8")
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)

    assert dispatcher._dropped_store.counts == {}
    assert not dropped_state_path.exists()


def test_malformed_persisted_dropped_state_is_cleared(tmp_path) -> None:
    dropped_state_path = tmp_path / "memory_brief_status_dropped_aggregates.json"
    dropped_state_path.write_text("{malformed json", encoding="utf-8")
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
        dropped_state_path=str(dropped_state_path),
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)

    assert dispatcher._dropped_store.counts == {}
    assert not dropped_state_path.exists()


@pytest.mark.asyncio
async def test_stop_flushes_pending_dropped_aggregates_after_worker_exit() -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=mock_response)
    client.aclose = AsyncMock()
    dispatcher._client = client
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    dispatcher._worker_task = asyncio.create_task(asyncio.sleep(0))

    await dispatcher.stop()

    assert dispatcher._client is None
    assert dispatcher._worker_task is None
    assert dispatcher._dropped_store.counts == {}
    assert client.post.await_count == 1
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_warns_when_pending_dropped_aggregates_remain_unsent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = MemoryBriefStatusTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
        allowed_phases=_ALLOWED_PHASES,
    )
    dispatcher = MemoryBriefStatusTelemetryDispatcher(config)
    client = MagicMock()
    client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
        ]
    )
    client.aclose = AsyncMock()
    dispatcher._client = client
    dispatcher._record_drop(dropped_phase="stream", incoming_phase="persist")
    dispatcher._worker_task = asyncio.create_task(asyncio.sleep(0))

    with caplog.at_level(logging.WARNING):
        await dispatcher.stop()

    assert dispatcher._dropped_store.counts == {("stream", "persist"): 1}
    assert "stopped with pending dropped aggregates unsent" in caplog.text
    assert client.post.await_count == 2
    client.aclose.assert_awaited_once()


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

    try:
        await start_memory_brief_status_telemetry_dispatcher()
        assert telemetry_dispatcher._dispatcher is not None

        enqueue_memory_brief_status_telemetry(
            phase="stream",
            payload={"state": "ready"},
        )

        await stop_memory_brief_status_telemetry_dispatcher()
        assert telemetry_dispatcher._dispatcher is None
    finally:
        monkeypatch.setattr(telemetry_dispatcher, "_dispatcher", None)


def test_enqueue_helper_passes_phase_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatcher = MagicMock()
    monkeypatch.setattr(telemetry_dispatcher, "_dispatcher", dispatcher)

    enqueue_memory_brief_status_telemetry(
        phase="stream",
        payload={"state": "ready"},
    )

    dispatcher.enqueue.assert_called_once_with("stream", {"state": "ready"})
