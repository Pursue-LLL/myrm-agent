"""Tests for context compaction telemetry dispatcher."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.services.agent.context_compaction_telemetry as telemetry
from app.config.settings import (
    ContextCompactionTelemetrySettings,
    ControlPlaneSettings,
    settings,
)
from app.schemas.control_plane import ContextCompactionSnapshot
from app.services.agent.context_compaction_telemetry import (
    ContextCompactionTelemetryConfig,
    ContextCompactionTelemetryDispatcher,
    ContextCompactionTelemetryEnvelope,
    _build_context_compaction_envelope,
    enqueue_context_compaction_telemetry,
    start_context_compaction_telemetry_dispatcher,
    stop_context_compaction_telemetry_dispatcher,
)


def _patch_telemetry_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str = "",
    telemetry_token: str = "",
    telemetry_subject: str = "",
    batch_size: int = 16,
    flush_interval_seconds: float = 2.0,
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
        "context_compaction_telemetry",
        ContextCompactionTelemetrySettings(
            batch_size=batch_size,
            flush_interval_seconds=flush_interval_seconds,
            queue_size=queue_size,
        ),
    )


@pytest.mark.asyncio
async def test_dispatcher_batches_multiple_snapshots() -> None:
    config = ContextCompactionTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = ContextCompactionTelemetryDispatcher(config)

    with patch("app.services.agent.context_compaction_telemetry.get_task_metrics") as get_metrics:
        metrics = MagicMock()
        metrics.compression_count = 1
        metrics.to_dict.side_effect = [
            {"compression_count": 1, "total_tokens_saved": 10, "compression_events": []},
            {"compression_count": 1, "total_tokens_saved": 20, "compression_events": []},
        ]
        get_metrics.return_value = metrics

        dispatcher._flush_batch = AsyncMock()
        await dispatcher.start()
        dispatcher.enqueue("chat-1")
        dispatcher.enqueue("chat-2")
        await asyncio.sleep(0.05)
        await dispatcher.stop()

    dispatcher._flush_batch.assert_called()
    flushed_batch = dispatcher._flush_batch.await_args_list[0].args[0]
    assert len(flushed_batch) == 2
    assert [item.chat_id for item in flushed_batch] == ["chat-1", "chat-2"]


def test_partial_env_config_disables_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(
        monkeypatch,
        url="http://control-plane:8001",
        telemetry_token="",
        telemetry_subject="sandbox-42",
    )

    assert ContextCompactionTelemetryConfig.from_settings() is None


def test_empty_env_config_disables_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_telemetry_settings(monkeypatch)

    assert ContextCompactionTelemetryConfig.from_settings() is None


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

    config = ContextCompactionTelemetryConfig.from_settings()

    assert config is not None
    assert config.control_plane_url == "http://control-plane:8001"
    assert config.batch_size == 16
    assert config.flush_interval_seconds == 2.0
    assert config.queue_size == 256


def test_context_compaction_snapshot_preserves_content_blind_metadata() -> None:
    raw: dict[str, object] = {
        "compression_count": 1,
        "total_tokens_saved": 100,
        "refetch_events": [
            {
                "timestamp": "2026-05-19T00:00:00+00:00",
                "archive_path": "",
                "has_archive_path": True,
            }
        ],
        "archive_restore_outcome_events": [
            {
                "timestamp": "2026-05-19T00:00:01+00:00",
                "archive_path": "",
                "has_archive_path": True,
                "recorded": True,
                "is_range_read": True,
            }
        ],
        "archive_restore_result_events": [
            {
                "timestamp": "2026-05-19T00:00:02+00:00",
                "archive_path": "",
                "restore_arg": "",
                "has_archive_path": True,
                "has_restore_arg": True,
                "estimated_tokens": 32,
            }
        ],
        "archive_restore_block_events": [
            {
                "timestamp": "2026-05-19T00:00:03+00:00",
                "archive_path": "",
                "has_archive_path": True,
                "primary_restore_arg": "",
                "has_primary_restore_arg": True,
                "recommended_ranges": [],
                "recommended_range_count": 2,
                "restore_range_hints": [],
                "restore_range_hint_count": 3,
                "content_features": [
                    {
                        "feature_type": "json_keys",
                        "count": 2,
                        "values": [],
                        "value_count": 2,
                    }
                ],
                "content_feature_count": 4,
            }
        ],
    }

    snapshot = ContextCompactionSnapshot.from_mapping(raw)
    payload = snapshot.model_dump()
    refetch_event = payload["refetch_events"][0]
    outcome_event = payload["archive_restore_outcome_events"][0]
    result_event = payload["archive_restore_result_events"][0]
    block_event = payload["archive_restore_block_events"][0]
    feature = block_event["content_features"][0]

    assert refetch_event["has_archive_path"] is True
    assert outcome_event["has_archive_path"] is True
    assert result_event["has_archive_path"] is True
    assert result_event["has_restore_arg"] is True
    assert block_event["has_archive_path"] is True
    assert block_event["has_primary_restore_arg"] is True
    assert block_event["recommended_range_count"] == 2
    assert block_event["restore_range_hint_count"] == 3
    assert block_event["content_feature_count"] == 4
    assert feature["values"] == []
    assert feature["value_count"] == 2


def test_build_envelope_requires_positive_metrics() -> None:
    config = ContextCompactionTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
    )

    with patch("app.services.agent.context_compaction_telemetry.get_task_metrics", return_value=None):
        assert _build_context_compaction_envelope("chat-1", config) is None

    empty_metrics = MagicMock()
    empty_metrics.compression_count = 0
    with patch("app.services.agent.context_compaction_telemetry.get_task_metrics", return_value=empty_metrics):
        assert _build_context_compaction_envelope("chat-1", config) is None

    rich_metrics = MagicMock()
    rich_metrics.compression_count = 2
    rich_metrics.to_dict.return_value = {
        "compression_count": 2,
        "total_tokens_saved": 128,
        "archive_restore_block_events": [
            {
                "reason": "archive_restore_range_required",
                "archive_path": ".context/chat-2/compacted/result.txt",
                "primary_restore_arg": ".context/chat-2/compacted/result.txt:1-20",
                "recommended_ranges": [".context/chat-2/compacted/result.txt:1-20"],
                "restore_range_hints": [
                    {
                        "range_arg": ".context/chat-2/compacted/result.txt:1-20",
                        "reason": "error_keyword",
                        "start_line": 1,
                        "end_line": 20,
                        "line": 3,
                    }
                ],
                "content_features": [
                    {
                        "feature_type": "json_keys",
                        "count": 2,
                        "values": ["secret", "token"],
                    }
                ],
            }
        ],
        "archive_restore_result_events": [
            {
                "archive_path": ".context/chat-2/compacted/result.txt",
                "restore_arg": ".context/chat-2/compacted/result.txt:1-20",
                "estimated_tokens": 32,
                "restored_line_count": 20,
            }
        ],
    }
    with patch("app.services.agent.context_compaction_telemetry.get_task_metrics", return_value=rich_metrics):
        envelope = _build_context_compaction_envelope("chat-2", config)

    assert envelope is not None
    assert envelope.chat_id == "chat-2"
    assert envelope.snapshot.compression_count == 2
    assert envelope.snapshot.total_tokens_saved == 128
    snapshot_payload = envelope.snapshot.model_dump()
    snapshot_json = envelope.snapshot.model_dump_json()
    block_event = snapshot_payload["archive_restore_block_events"][0]
    result_event = snapshot_payload["archive_restore_result_events"][0]
    assert ".context/chat-2/compacted/result.txt" not in snapshot_json
    assert "secret" not in snapshot_json
    assert block_event["has_archive_path"] is True
    assert block_event["has_primary_restore_arg"] is True
    assert block_event["recommended_range_count"] == 1
    assert block_event["restore_range_hint_count"] == 1
    assert block_event["content_feature_count"] == 1
    assert result_event["has_restore_arg"] is True


def test_enqueue_drops_oldest_snapshot_when_queue_full(caplog: pytest.LogCaptureFixture) -> None:
    config = ContextCompactionTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=1,
    )
    dispatcher = ContextCompactionTelemetryDispatcher(config)

    first_metrics = MagicMock()
    first_metrics.compression_count = 1
    first_metrics.to_dict.return_value = {"compression_count": 1}
    second_metrics = MagicMock()
    second_metrics.compression_count = 1
    second_metrics.to_dict.return_value = {"compression_count": 2}

    with (
        caplog.at_level(logging.WARNING),
        patch(
            "app.services.agent.context_compaction_telemetry.get_task_metrics",
            side_effect=[first_metrics, second_metrics],
        ),
    ):
        dispatcher.enqueue("chat-1")
        dispatcher.enqueue("chat-2")

    retained = dispatcher._queue.get_nowait()
    assert retained.chat_id == "chat-2"
    assert retained.snapshot.compression_count == 2
    assert "dropping oldest snapshot for chat chat-1" in caplog.text


@pytest.mark.asyncio
async def test_flush_batch_retries_then_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    config = ContextCompactionTelemetryConfig(
        control_plane_url="http://control-plane:8001",
        telemetry_token="secret-token",
        telemetry_subject="sandbox-42",
        batch_size=4,
        flush_interval_seconds=0.01,
        queue_size=16,
    )
    dispatcher = ContextCompactionTelemetryDispatcher(config)
    dispatcher._client = AsyncMock()
    dispatcher._client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://control-plane:8001")),
        ]
    )
    batch = [
        ContextCompactionTelemetryEnvelope(
            telemetry_subject="sandbox-42",
            chat_id="chat-1",
            timestamp="2026-04-18T00:00:00+00:00",
            snapshot={"compression_count": 1},
        )
    ]

    with caplog.at_level(logging.WARNING):
        await dispatcher._flush_batch(batch)

    assert dispatcher._client.post.await_count == 2
    first_call = dispatcher._client.post.await_args_list[0]
    assert first_call.kwargs["headers"]["X-Telemetry-Subject"] == "sandbox-42"
    assert "events" in first_call.kwargs["json"]
    assert "items" not in first_call.kwargs["json"]
    assert "Failed to flush 1 context compaction telemetry items" in caplog.text


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
        await start_context_compaction_telemetry_dispatcher()
        assert telemetry._dispatcher is not None

        with patch("app.services.agent.context_compaction_telemetry.get_task_metrics", return_value=None):
            enqueue_context_compaction_telemetry("chat-noop")

        await stop_context_compaction_telemetry_dispatcher()
        assert telemetry._dispatcher is None
    finally:
        monkeypatch.setattr(telemetry, "_dispatcher", None)
