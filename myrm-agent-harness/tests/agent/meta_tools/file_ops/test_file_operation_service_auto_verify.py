"""Unit tests for the Auto-Verify report FileOperationService appends after a CREATE and a STR_REPLACE."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

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
async def test_create_appends_the_auto_verify_report() -> None:
    """CREATE runs auto_verify and appends its report."""
    executor = AsyncMock()
    context = OperationContext(
        operation=OperationType.CREATE,
        executor=executor,
        path="/workspace/main.py",
        file_text="x: int = 'bad'\n",
    )
    service = FileOperationService(context)

    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
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
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.check_conflict_pre_write",
                return_value=None,
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.validators.delta_syntax_validator.DeltaSyntaxValidator.validate",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
                return_value=None,
            )
        )
        stack.enter_context(
            patch.object(
                service.observer_manager,
                "notify_file_created",
                new_callable=AsyncMock,
            )
        )
        mock_auto_verify = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.validators.auto_verify.run_auto_verify",
                new_callable=AsyncMock,
                return_value="\n[Auto-Verify] Type errors detected, please fix:\n  main.py:1:1 - error: Type mismatch",
            )
        )
        strategy = AsyncMock()
        strategy.exists = AsyncMock(return_value=False)
        strategy.read_file = AsyncMock(return_value=["x: int = 'bad'"])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()

        result = await service.execute()

    assert "[Auto-Verify]" in result
    assert "Type mismatch" in result
    mock_auto_verify.assert_called_once_with(executor, "/workspace/main.py", edit_line_start=None, edit_line_end=None)


@pytest.mark.asyncio
async def test_str_replace_triggers_auto_verify_with_line_range() -> None:
    """STR_REPLACE runs auto_verify with the edited line range."""
    executor = AsyncMock()
    context = str_replace_ctx(
        executor=executor,
        path="/workspace/main.py",
        old_str="x = 1",
        new_str="x: str = 1",
    )
    service = FileOperationService(context)

    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
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
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.check_conflict_pre_write",
                return_value=None,
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.get_file_integrity_guard",
                return_value=None,
            )
        )
        stack.enter_context(
            patch.object(
                service.observer_manager,
                "notify_file_modified",
                new_callable=AsyncMock,
            )
        )
        mock_auto_verify = stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.validators.auto_verify.run_auto_verify",
                new_callable=AsyncMock,
                return_value="\n[Auto-Verify] Type errors detected, please fix:\n  main.py:5:1 - error: Incompatible types",
            )
        )
        strategy = AsyncMock()
        strategy.exists = AsyncMock(return_value=True)
        strategy.read_file = AsyncMock(return_value=["line1", "line2", "line3", "line4", "x = 1", "line6"])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()

        result = await service.execute()

    assert "[Auto-Verify]" in result
    assert "Incompatible types" in result
    mock_auto_verify.assert_called_once_with(executor, "/workspace/main.py", edit_line_start=5, edit_line_end=5)
