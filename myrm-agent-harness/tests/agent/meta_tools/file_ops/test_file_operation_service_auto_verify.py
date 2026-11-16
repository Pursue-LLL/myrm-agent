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
async def test_create_triggers_auto_verify_when_no_verify_command() -> None:
    """CREATE without verify_command triggers auto_verify and appends report."""
    executor = AsyncMock()
    context = OperationContext(
        operation=OperationType.CREATE,
        executor=executor,
        path="/workspace/main.py",
        file_text="x: int = 'bad'\n",
        verify_command=None,
    )
    service = FileOperationService(context)

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
async def test_create_skips_auto_verify_when_verify_command_present() -> None:
    """CREATE with explicit verify_command skips auto_verify entirely."""
    executor = AsyncMock()
    exec_result = AsyncMock()
    exec_result.success = True
    exec_result.exit_code = 0
    exec_result.stdout = ""
    exec_result.stderr = ""
    executor.execute_bash.return_value = exec_result

    context = OperationContext(
        operation=OperationType.CREATE,
        executor=executor,
        path="/workspace/main.py",
        file_text="x: int = 1\n",
        verify_command="pyright /workspace/main.py",
    )
    service = FileOperationService(context)

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
            )
        )
        strategy = AsyncMock()
        strategy.exists = AsyncMock(return_value=False)
        strategy.read_file = AsyncMock(return_value=["x: int = 1"])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()

        result = await service.execute()

    assert "[Auto-Verify]" not in result
    mock_auto_verify.assert_not_called()


@pytest.mark.asyncio
async def test_str_replace_triggers_auto_verify_with_line_range() -> None:
    """STR_REPLACE without verify_command triggers auto_verify with edit range."""
    executor = AsyncMock()
    context = str_replace_ctx(
        executor=executor,
        path="/workspace/main.py",
        old_str="x = 1",
        new_str="x: str = 1",
        verify_command=None,
    )
    service = FileOperationService(context)

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
