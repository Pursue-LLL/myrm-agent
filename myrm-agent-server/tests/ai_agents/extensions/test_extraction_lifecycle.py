"""Tests for extraction lifecycle observer bridge."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory import (
    MemoryOperationKind,
    MemoryOperationStatus,
)

from app.ai_agents.extensions.extraction_lifecycle import (
    make_extraction_lifecycle_observer,
)


@pytest.mark.asyncio
async def test_observer_records_extract_pending_to_ledger() -> None:
    observer = make_extraction_lifecycle_observer("chat-99")
    mock_row = MagicMock()
    mock_ledger = MagicMock()
    mock_ledger.record_event = AsyncMock(return_value=mock_row)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
    ):
        await observer(
            "extract",
            MemoryOperationStatus.PENDING,
            chat_id="chat-99",
            summary="Memory extraction started",
        )

    mock_ledger.record_event.assert_awaited_once()
    call_kwargs = mock_ledger.record_event.await_args.kwargs
    assert call_kwargs["kind"] == MemoryOperationKind.EXTRACT
    assert call_kwargs["status"] == MemoryOperationStatus.PENDING
    assert call_kwargs["target_id"] == "chat-99"
    assert call_kwargs["metadata"]["chat_id"] == "chat-99"


@pytest.mark.asyncio
async def test_observer_publishes_toast_on_extract_success_with_cards() -> None:
    observer = make_extraction_lifecycle_observer("chat-99")
    mock_row = MagicMock()
    mock_ledger = MagicMock()
    mock_ledger.record_event = AsyncMock(return_value=mock_row)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_bus = MagicMock()

    with (
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=mock_bus),
    ):
        await observer(
            "extract",
            MemoryOperationStatus.SUCCESS,
            chat_id="chat-99",
            summary="Extracted 2 memory cards",
            metadata={"stored_count": 2},
        )

    mock_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_observer_publishes_toast_on_extract_success_with_verbatim_only() -> None:
    observer = make_extraction_lifecycle_observer("chat-99")
    mock_row = MagicMock()
    mock_ledger = MagicMock()
    mock_ledger.record_event = AsyncMock(return_value=mock_row)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_bus = MagicMock()

    with (
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=mock_bus),
    ):
        await observer(
            "extract",
            MemoryOperationStatus.SUCCESS,
            chat_id="chat-99",
            summary="Stored verbatim memory chunks",
            metadata={"stored_count": 0, "verbatim_count": 1},
        )

    mock_bus.publish.assert_called_once()
    publish_payload = mock_bus.publish.call_args.args[0].data
    assert publish_payload["count"] == 1


@pytest.mark.asyncio
async def test_observer_skips_toast_when_extract_success_has_no_cards() -> None:
    observer = make_extraction_lifecycle_observer("chat-99")
    mock_ledger = MagicMock()
    mock_ledger.record_event = AsyncMock(return_value=MagicMock())

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_bus = MagicMock()

    with (
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=mock_bus),
    ):
        await observer(
            "extract",
            MemoryOperationStatus.SUCCESS,
            chat_id="chat-99",
            summary="No memories extracted",
            metadata={"stored_count": 0, "verbatim_count": 0},
        )

    mock_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_manual_retry_observer_uses_custom_source_and_metadata() -> None:
    observer = make_extraction_lifecycle_observer(
        "chat-99",
        source="manual_retry_extract",
        is_retry=True,
    )
    mock_ledger = MagicMock()
    mock_ledger.record_event = AsyncMock(return_value=MagicMock())

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
    ):
        await observer(
            "extract",
            MemoryOperationStatus.PENDING,
            chat_id="chat-99",
            summary="Manual retry started",
        )

    call_kwargs = mock_ledger.record_event.await_args.kwargs
    assert call_kwargs["source"] == "manual_retry_extract"
    assert call_kwargs["metadata"]["is_retry"] is True


@patch("app.services.memory.extract_retry.extract_retry_queue.enqueue", new_callable=AsyncMock)
@patch("app.database.connection.get_session")
@patch("app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService")
@pytest.mark.asyncio
async def test_auto_extract_error_enqueues_retry(
    mock_ledger_cls, mock_session_factory, mock_enqueue
) -> None:
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session
    mock_ledger_cls.return_value.record_event = AsyncMock(return_value=MagicMock())

    observer = make_extraction_lifecycle_observer("chat-99")
    await observer(
        "extract",
        MemoryOperationStatus.ERROR,
        chat_id="chat-99",
        summary="Memory extraction failed",
        metadata={"error": "TimeoutError"},
    )

    mock_enqueue.assert_awaited_once_with("chat-99", reset_failed=False)


@patch("app.services.memory.extract_retry.extract_retry_queue.enqueue", new_callable=AsyncMock)
@patch("app.database.connection.get_session")
@patch("app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService")
@pytest.mark.asyncio
async def test_manual_retry_error_does_not_enqueue_again(
    mock_ledger_cls, mock_session_factory, mock_enqueue
) -> None:
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = mock_session
    mock_ledger_cls.return_value.record_event = AsyncMock(return_value=MagicMock())

    observer = make_extraction_lifecycle_observer(
        "chat-99",
        source="manual_retry_extract",
        is_retry=True,
    )
    await observer(
        "extract",
        MemoryOperationStatus.ERROR,
        chat_id="chat-99",
        summary="Manual retry failed",
        metadata={"error": "TimeoutError"},
    )

    mock_enqueue.assert_not_awaited()
