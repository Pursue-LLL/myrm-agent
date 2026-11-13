"""Unit tests for FileViewService: directory listings, archive read guards, error handling, read recording."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG, FileIOConfig
from myrm_agent_harness.agent.context_management.infra.session_lock import (
    reset_current_chat_id,
    set_current_chat_id,
)
from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
    ArchiveRefetchDecision,
    clear_task_metrics,
    create_task_metrics,
    get_task_metrics,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.archive_restore_guard import (
    parse_archive_restore_block_payload,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service import (
    FileOperationService,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_view_service import FileViewService
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import (
    OperationContext,
    OperationType,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.read_semaphore import (
    get_read_semaphore,
)
from myrm_agent_harness.agent.meta_tools.file_ops.observers.observer_manager import ObserverManager

_MODULE = "myrm_agent_harness.agent.meta_tools.file_ops.core.file_view_service"


def _view_service(context: OperationContext, io_config: FileIOConfig | None = None) -> FileViewService:
    return FileViewService(context, io_config or DEFAULT_FILE_IO_CONFIG, ObserverManager())


@pytest.mark.asyncio
async def test_file_operation_service_delegates_view_to_view_service() -> None:
    context = OperationContext(operation=OperationType.VIEW, paths=["a.txt"], executor=None)
    service = FileOperationService(context)
    with (
        patch.object(context, "validate"),
        patch.object(FileViewService, "execute", new_callable=AsyncMock, return_value="viewed") as execute,
    ):
        assert await service.execute() == "viewed"
    execute.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_execute_view_with_read_error() -> None:
    context = OperationContext(operation=OperationType.VIEW, paths=["error.txt"], executor=None)
    service = _view_service(context)
    with patch.object(service, "_view_single_path", side_effect=Exception("Read failure")):
        result = await service.execute()

    assert "Error reading error.txt: Read failure" in result


@pytest.mark.asyncio
async def test_execute_view_directory() -> None:
    context = OperationContext(operation=OperationType.VIEW, paths=["/some/dir"], executor=None)
    service = _view_service(context)

    with (
        patch(f"{_MODULE}.FileSystemStrategyFactory.create_strategy") as mock_factory,
        patch(f"{_MODULE}.ValidatorChain") as mock_validator,
    ):
        mock_strategy = AsyncMock()
        mock_strategy.is_directory.return_value = True
        mock_strategy.list_directory.return_value = [("file1.txt", False, 128)]
        mock_factory.return_value = mock_strategy
        mock_validator_instance = AsyncMock()
        mock_validator.return_value = mock_validator_instance

        result = await service.execute()

    assert "/some/dir:" in result
    assert "file1.txt" in result


@pytest.mark.asyncio
async def test_get_read_semaphore_fallback_when_no_running_loop() -> None:
    io_config = FileIOConfig(max_concurrent_reads=3)
    with patch("asyncio.get_running_loop", side_effect=RuntimeError("no running event loop")):
        sem = await get_read_semaphore(io_config)
    assert isinstance(sem, asyncio.Semaphore)


@pytest.mark.asyncio
async def test_execute_view_warns_when_paths_exceed_concurrency(
    caplog: pytest.LogCaptureFixture,
) -> None:
    context = OperationContext(
        operation=OperationType.VIEW,
        paths=["a.txt", "b.txt", "c.txt"],
        executor=None,
    )
    service = _view_service(context, FileIOConfig(max_concurrent_reads=2))
    with (
        caplog.at_level(logging.WARNING),
        patch.object(
            service,
            "_view_single_path",
            new_callable=AsyncMock,
            side_effect=lambda p: f"ok:{p}",
        ),
    ):
        await service.execute()
    assert any("Concurrent read count" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_execute_view_regular_file_content() -> None:
    context = OperationContext(operation=OperationType.VIEW, paths=["doc.py"], executor=None)
    service = _view_service(context)
    with (
        patch(f"{_MODULE}.FileSystemStrategyFactory.create_strategy") as mock_factory,
        patch(f"{_MODULE}.ValidatorChain") as mock_vc,
        patch(f"{_MODULE}.get_file_integrity_guard", return_value=None),
    ):
        mock_strategy = AsyncMock()
        mock_strategy.is_directory.return_value = False
        mock_strategy.read_file.return_value = ["alpha", "beta"]
        mock_factory.return_value = mock_strategy
        mock_vc.return_value.validate = AsyncMock()
        result = await service.execute()
    assert "alpha" in result
    assert "beta" in result


@pytest.mark.asyncio
async def test_execute_view_blocks_archive_read_when_budget_denies() -> None:
    context = OperationContext(
        operation=OperationType.VIEW,
        paths=[".context/chat/compacted/result.txt:1-1"],
        executor=None,
    )
    service = _view_service(context)
    with (
        patch(f"{_MODULE}.FileSystemStrategyFactory.create_strategy") as mock_factory,
        patch(f"{_MODULE}.ValidatorChain") as mock_vc,
        patch(
            # Lazy in-function import: patch the source module (the function
            # rebinds from it on every call), not the importing module.
            "myrm_agent_harness.agent.context_management.tracking.archive_restore_runtime.evaluate_archive_refetch_for_path",
            return_value=ArchiveRefetchDecision(
                is_archive_path=True,
                allowed=False,
                recorded=False,
                reason="archive_refetch_path_budget_exceeded",
                message="Archived context restore blocked because this path reached the per-task read limit.",
                suggested_action="Use a narrower line range or continue from the existing archive summary.",
            ),
        ),
    ):
        mock_strategy = AsyncMock()
        mock_strategy.is_directory.return_value = False
        mock_strategy.read_file.return_value = ["archived line"]
        mock_factory.return_value = mock_strategy
        mock_vc.return_value.validate = AsyncMock()
        result = await service.execute()

    assert "Archive restore blocked." in result
    assert '"reason": "archive_refetch_path_budget_exceeded"' in result
    assert '"type": "archive_restore_blocked"' in result
    assert "archived line" not in result


@pytest.mark.asyncio
async def test_execute_view_blocks_large_full_archive_read_with_structured_metrics() -> None:
    chat_id = "chat_file_read_archive_range_required"
    archive_path = f".context/{chat_id}/compacted/result.txt"
    context = OperationContext(
        operation=OperationType.VIEW,
        paths=[archive_path],
        executor=None,
    )
    service = _view_service(context)
    token = set_current_chat_id(chat_id)
    create_task_metrics(chat_id)
    try:
        with (
            patch(f"{_MODULE}.FileSystemStrategyFactory.create_strategy") as mock_factory,
            patch(f"{_MODULE}.ValidatorChain") as mock_vc,
        ):
            mock_strategy = AsyncMock()
            mock_strategy.is_directory.return_value = False
            mock_strategy.get_file_size.return_value = 40_000
            mock_strategy.read_file.return_value = ["archive payload " * 4000]
            mock_factory.return_value = mock_strategy
            mock_vc.return_value.validate = AsyncMock()

            result = await service.execute()

        metrics = get_task_metrics(chat_id)
        assert "Archive restore blocked." in result
        assert '"reason": "archive_restore_range_required"' in result
        assert (
            '"primary_restore_arg": ".context/chat_file_read_archive_range_required/compacted/result.txt:1-200"'
            in result
        )
        mock_strategy.read_file.assert_not_awaited()
        assert metrics is not None
        assert metrics.archive_restore_blocked_count == 1
        event = metrics.archive_restore_block_events[0]
        assert event.reason == "archive_restore_range_required"
        assert "chunk_restore_args" in event.suggested_action
    finally:
        reset_current_chat_id(token)
        clear_task_metrics(chat_id)


@pytest.mark.asyncio
async def test_execute_view_fails_closed_when_archive_size_probe_fails() -> None:
    chat_id = "chat_file_read_archive_probe_failed"
    archive_path = f".context/{chat_id}/compacted/result.txt"
    context = OperationContext(
        operation=OperationType.VIEW,
        paths=[archive_path],
        executor=None,
    )
    service = _view_service(context)
    token = set_current_chat_id(chat_id)
    try:
        with (
            patch(f"{_MODULE}.FileSystemStrategyFactory.create_strategy") as mock_factory,
            patch(f"{_MODULE}.ValidatorChain") as mock_vc,
        ):
            mock_strategy = AsyncMock()
            mock_strategy.is_directory.return_value = False
            mock_strategy.get_file_size.side_effect = OSError("permission denied")
            mock_strategy.read_file.return_value = ["archive payload"]
            mock_factory.return_value = mock_strategy
            mock_vc.return_value.validate = AsyncMock()

            result = await service.execute()

            assert "Archive restore blocked." in result
            assert '"reason": "archive_restore_size_probe_failed"' in result
            payload = parse_archive_restore_block_payload(result)
            assert payload is not None
            assert payload["reason"] == "archive_restore_size_probe_failed"
            assert payload["type"] == "archive_restore_blocked"
            assert "archive payload" not in result
            mock_strategy.read_file.assert_not_awaited()
    finally:
        reset_current_chat_id(token)


@pytest.mark.asyncio
async def test_execute_view_records_read_when_integrity_guard_active() -> None:
    context = OperationContext(operation=OperationType.VIEW, paths=["tracked.py"], executor=None)
    service = _view_service(context)
    guard = MagicMock()
    with (
        patch(f"{_MODULE}.FileSystemStrategyFactory.create_strategy") as mock_factory,
        patch(f"{_MODULE}.ValidatorChain") as mock_vc,
        patch(f"{_MODULE}.get_file_integrity_guard", return_value=guard),
    ):
        mock_strategy = AsyncMock()
        mock_strategy.is_directory.return_value = False
        mock_strategy.read_file.return_value = ["line"]
        mock_factory.return_value = mock_strategy
        mock_vc.return_value.validate = AsyncMock()
        await service.execute()
    guard.record_read.assert_called_once_with("tracked.py", "line")
