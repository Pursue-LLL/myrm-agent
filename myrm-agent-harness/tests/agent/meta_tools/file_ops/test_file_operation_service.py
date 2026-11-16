"""Unit tests for FileOperationService dispatch, CREATE and STR_REPLACE.

VIEW is covered by test_file_view_service.py, the write gates by test_file_operation_service_gates.py and the
Auto-Verify report by test_file_operation_service_auto_verify.py.
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
async def test_execute_unknown_operation() -> None:
    context = OperationContext(operation=OperationType.VIEW, paths=["test.txt"], executor=None)
    service = FileOperationService(context)
    with (
        patch.object(context, "validate"),
        patch.object(service.context, "operation", new="not_a_real_operation"),
        pytest.raises(ValueError, match="Unknown operation"),
    ):
        await service.execute()


@pytest.mark.asyncio
async def test_execute_create_missing_params() -> None:
    context = OperationContext(
        operation=OperationType.CREATE,
        executor=None,
        path="test.txt",
        file_text=None,
    )
    service = FileOperationService(context)
    with (
        patch.object(context, "validate"),
        pytest.raises(
            ValueError,
            match="CREATE operation requires 'path' and 'file_text' parameters",
        ),
    ):
        await service.execute()


@pytest.mark.asyncio
async def test_execute_str_replace_missing_params() -> None:
    context = OperationContext(
        operation=OperationType.STR_REPLACE,
        executor=None,
        path="test.txt",
        edits=(),
    )
    service = FileOperationService(context)
    with (
        patch.object(context, "validate"),
        pytest.raises(
            ValueError,
            match=r"STR_REPLACE operation requires 'path' and non-empty 'edits' parameters",
        ),
    ):
        await service.execute()


@pytest.mark.asyncio
async def test_execute_create_appends_conflict_notice() -> None:
    context = OperationContext(
        operation=OperationType.CREATE,
        executor=None,
        path="/w/note.txt",
        file_text="hello\n",
    )
    service = FileOperationService(context)
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/w/note.txt",
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
                return_value="Non-blocking conflict notice",
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
        strategy = AsyncMock()
        strategy.exists = AsyncMock(return_value=False)
        strategy.read_file = AsyncMock(return_value=["hello"])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()
        result = await service.execute()
    assert "Non-blocking conflict notice" in result


@pytest.mark.asyncio
async def test_execute_create_notifies_a_created_file_with_what_was_written() -> None:
    service_module = "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service"
    context = OperationContext(operation=OperationType.CREATE, executor=None, path="/w/new.txt", file_text="hello\n")
    service = FileOperationService(context)
    strategy = AsyncMock()
    strategy.read_file = AsyncMock(return_value=["hello", ""])
    with (
        patch.object(context, "validate"),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
            return_value="/w/new.txt",
        ),
        patch(f"{service_module}.FileSystemStrategyFactory.create_strategy", return_value=strategy),
        patch(f"{service_module}.ValidatorChain") as validator_chain,
        patch(f"{service_module}.check_conflict_pre_write", return_value=None),
        patch(f"{service_module}.get_file_integrity_guard", return_value=None),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.validators.delta_syntax_validator.DeltaSyntaxValidator.validate"
        ),
        patch.object(service.observer_manager, "notify_file_created", new_callable=AsyncMock) as created,
        patch.object(service.observer_manager, "notify_file_modified", new_callable=AsyncMock) as modified,
    ):
        validator_chain.return_value.validate = AsyncMock()
        await service.execute()

    strategy.write_file.assert_awaited_once_with("/w/new.txt", "hello\n")
    created.assert_awaited_once_with("/w/new.txt", "hello\n")
    modified.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_str_replace_delta_failure_rolls_back() -> None:
    context = str_replace_ctx(executor=None, path="/w/a.py")
    service = FileOperationService(context)
    old_flat = "old"
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/w/a.py",
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
                return_value=None,
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
                side_effect=ValueError("delta failed"),
            )
        )
        strategy = AsyncMock()
        strategy.read_file = AsyncMock(side_effect=[["old"], ["broken"]])
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()
        with pytest.raises(ValueError, match="delta failed"):
            await service.execute()
        assert strategy.write_file.await_count == 2
        strategy.write_file.assert_any_await("/w/a.py", old_flat)


@pytest.mark.asyncio
async def test_execute_str_replace_preserves_vault_frontmatter(tmp_path) -> None:
    """STR_REPLACE on vault .md must reinject YAML frontmatter dropped by the edit."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    note = vault / "daily.md"
    note.write_text(
        "---\ndate: 2026-07-28\n---\n# Daily\n\nOld body\n",
        encoding="utf-8",
    )
    context = str_replace_ctx(
        executor=None,
        path=str(note),
        old_str="---\ndate: 2026-07-28\n---\n# Daily\n\nOld body",
        new_str="# Daily\n\nUpdated journal",
    )
    service = FileOperationService(context)
    written: list[str] = []

    async def capture_write(_path: str, content: str) -> None:
        written.append(content)

    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value=str(note),
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
                return_value=None,
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
            patch.object(
                service.observer_manager,
                "notify_file_modified",
                new_callable=AsyncMock,
            )
        )
        strategy = AsyncMock()
        old_lines = note.read_text(encoding="utf-8").splitlines()
        strategy.read_file = AsyncMock(
            side_effect=[
                old_lines,
                old_lines,
            ]
        )
        strategy.write_file = AsyncMock(side_effect=capture_write)
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()

        result = await service.execute()

    assert written, "write_file should have been called"
    assert "date: 2026-07-28" in written[0]
    assert "Updated journal" in written[0]
    assert "Vault: Preserved YAML frontmatter" in result


@pytest.mark.asyncio
async def test_execute_str_replace_appends_conflict_warning() -> None:
    context = str_replace_ctx(executor=None, path="/w/a.py")
    service = FileOperationService(context)
    guard = MagicMock()
    guard.require_read_before_write.return_value = None
    guard.require_full_read_before_edit.return_value = None
    guard.require_version_match.return_value = None
    guard.record_write = MagicMock()
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value="/w/a.py",
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
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service.check_conflict_pre_write",
                return_value="Concurrent edit notice",
            )
        )
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.validators.delta_syntax_validator.DeltaSyntaxValidator.validate",
            )
        )
        stack.enter_context(
            patch.object(
                service.observer_manager,
                "notify_file_modified",
                new_callable=AsyncMock,
            )
        )
        strategy = AsyncMock()
        strategy.read_file = AsyncMock(
            side_effect=[
                ["old"],
                ["new_final"],
            ]
        )
        mock_factory.return_value = strategy
        mock_vc.return_value.validate = AsyncMock()
        result = await service.execute()
    assert "Concurrent edit notice" in result
    assert "Stale file warning" not in result
