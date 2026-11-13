"""Unit tests for FileOperationService dispatch, CREATE and STR_REPLACE (VIEW: test_file_view_service.py)."""

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
    StrReplaceEdit,
)


def _str_replace_ctx(
    *,
    path: str,
    old_str: str = "old",
    new_str: str = "new",
    edits: tuple[StrReplaceEdit, ...] | None = None,
    **kwargs: object,
) -> OperationContext:
    if edits is None:
        edits = (StrReplaceEdit(old_str=old_str, new_str=new_str),)
    return OperationContext(
        operation=OperationType.STR_REPLACE,
        path=path,
        edits=edits,
        **kwargs,
    )


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
    context = _str_replace_ctx(executor=None, path="/w/a.py")
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
    context = _str_replace_ctx(
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
    context = _str_replace_ctx(executor=None, path="/w/a.py")
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


@pytest.mark.asyncio
async def test_execute_str_replace_rejects_unread_file() -> None:
    """Gate rejects edits on files never read in the session."""
    context = _str_replace_ctx(executor=None, path="/w/unread.py")
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
    context = _str_replace_ctx(executor=None, path="/w/partial.py")
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
    context = _str_replace_ctx(executor=None, path="/w/stale.py")
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
    mock_auto_verify.assert_called_once_with(executor, "/workspace/main.py")


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
    context = _str_replace_ctx(
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


@pytest.mark.asyncio
async def test_file_operation_service_version_mismatch_raises_structured_tool_error() -> None:
    """Version mismatch from FileIntegrityGuard raises ToolError with self-healing payload."""
    from myrm_agent_harness.utils.errors import ToolError

    executor = AsyncMock()
    context = _str_replace_ctx(
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
