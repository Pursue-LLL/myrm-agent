"""Unit tests for the gates FileOperationService runs before a write.

Read-before-write, stale version and the read-only evidence directory.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service import (
    FileOperationService,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import (
    OperationContext,
    OperationType,
)
from tests.agent.meta_tools.file_ops.service_support import str_replace_ctx


@pytest.mark.asyncio
async def test_execute_str_replace_rejects_unread_file() -> None:
    """Gate rejects edits on files never read in the session."""
    context = str_replace_ctx(executor=None, path="/w/unread.py")
    service = FileOperationService(context)
    guard = MagicMock()
    guard.require_read_before_write.return_value = "File '/w/unread.py' has not been read in this session."
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/w/unread.py",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.FileSystemStrategyFactory.create_strategy",
            )
        )
        mock_vc = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.ValidatorChain",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
                return_value=guard,
            )
        )
        mock_vc.return_value.validate = AsyncMock()

        from myrm_agent_harness.utils.errors import ToolError

        with pytest.raises(ToolError) as exc_info:
            await service.execute()
        assert "has not been read" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_str_replace_rejects_partial_read() -> None:
    """Gate rejects edits after only a partial/range read."""
    context = str_replace_ctx(executor=None, path="/w/partial.py")
    service = FileOperationService(context)
    guard = MagicMock()
    guard.require_read_before_write.return_value = None
    guard.require_full_read_before_edit.return_value = "File '/w/partial.py' was only partially read in this session."
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/w/partial.py",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.FileSystemStrategyFactory.create_strategy",
            )
        )
        mock_vc = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.ValidatorChain",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
                return_value=guard,
            )
        )
        mock_vc.return_value.validate = AsyncMock()

        from myrm_agent_harness.utils.errors import ToolError

        with pytest.raises(ToolError) as exc_info:
            await service.execute()
        assert "partially read" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_str_replace_rejects_stale_version() -> None:
    """Gate rejects edits when on-disk content changed since full read."""
    context = str_replace_ctx(executor=None, path="/w/stale.py")
    service = FileOperationService(context)
    guard = MagicMock()
    guard.require_read_before_write.return_value = None
    guard.require_full_read_before_edit.return_value = None
    guard.require_version_match.return_value = "File '/w/stale.py' has changed on disk since your last read."
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/w/stale.py",
            )
        )
        mock_factory = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.FileSystemStrategyFactory.create_strategy",
            )
        )
        mock_vc = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.ValidatorChain",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
                return_value=guard,
            )
        )
        strategy = AsyncMock()
        strategy.read_file = AsyncMock(return_value=["stale on disk"])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()

        from myrm_agent_harness.utils.errors import ToolError

        with pytest.raises(ToolError) as exc_info:
            await service.execute()
        assert "changed on disk" in str(exc_info.value)


@pytest.mark.asyncio
async def test_file_operation_service_version_mismatch_raises_structured_tool_error() -> None:
    """Version mismatch from FileIntegrityGuard raises ToolError with self-healing payload."""
    from myrm_agent_harness.utils.errors import ToolError

    executor = AsyncMock()
    context = str_replace_ctx(
        executor=executor,
        path="/workspace/main.py",
        old_str="x = 1",
        new_str="x = 2",
    )
    service = FileOperationService(context)

    mock_guard = MagicMock()
    mock_guard.require_read_before_write.return_value = None
    mock_guard.require_full_read_before_edit.return_value = None
    mock_guard.require_version_match.return_value = (
        "File '/workspace/main.py' has changed on disk since your last read (content hash mismatch).\n"
        "Current disk content snippet:\n```\nx = 100\n```\n"
        "Rebase your edits directly on this current content without calling file_read_tool."
    )

    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/workspace/main.py",
            )
        )
        mock_factory = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.FileSystemStrategyFactory.create_strategy",
            )
        )
        mock_vc = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.ValidatorChain",
            )
        )
        strategy = AsyncMock()
        strategy.exists = AsyncMock(return_value=True)
        strategy.read_file = AsyncMock(return_value=["x = 100"])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()

        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
                return_value=mock_guard,
            )
        )

        with pytest.raises(ToolError) as exc_info:
            await service.execute()

        mock_guard.require_version_match.assert_called_once_with("/workspace/main.py", "x = 100", anchor=["x = 1"])
        err = exc_info.value
        assert err.error_code == "FILE_VERSION_MISMATCH"
        assert "Current disk content snippet" in str(err)
        assert err.diagnostic_info.get("error_category") == "version_conflict"
        assert "Call file_edit_tool again directly" in err.recovery_suggestions[2]


@pytest.mark.asyncio
async def test_evidence_readonly_validator_blocks_write_in_chain() -> None:
    """ValidatorChain blocks write attempts to evidence/ paths."""
    from myrm_agent_harness.agent.meta_tools.file_ops.validators.validator_chain import (
        ValidatorChain,
    )

    strategy = AsyncMock()
    chain = ValidatorChain(strategy)

    executor = AsyncMock()
    ctx = OperationContext(
        executor=executor,
        operation=OperationType.CREATE,
        path="/workspace/evidence/interview_raw.pdf",
    )
    with pytest.raises(PermissionError, match="resides in a read-only session evidence"):
        await chain.validate(ctx, "/workspace/evidence/interview_raw.pdf")

    # VIEW operation must be allowed
    view_ctx = OperationContext(
        executor=executor,
        operation=OperationType.VIEW,
        path="/workspace/evidence/interview_raw.pdf",
    )
    strategy.exists = AsyncMock(return_value=True)
    await chain.validate(view_ctx, "/workspace/evidence/interview_raw.pdf")
