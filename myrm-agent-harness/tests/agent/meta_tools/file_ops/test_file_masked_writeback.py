"""A write must not carry a mask of the redactor where the file holds a secret.

A read shows a secret as a mask (``***``, ``sk-pro...7890``). Text copied from that read and written back replaces the
real value on disk with the mask; the fuzzy edit strategies (``block_anchored``) and a whole-file create both accept it.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_integrity_guard import raise_if_masked_writeback
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service import FileOperationService
from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import (
    OperationContext,
    OperationType,
    StrReplaceEdit,
)
from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.utils.errors import ToolError

_SERVICE = "myrm_agent_harness.agent.meta_tools.file_ops.core.file_operation_service"
_SECRET_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
_ENV = "HOST=db\nDB_PASSWORD=hunter2hunter2xyz\nPORT=5432\nNAME=app\n"
_YAML = f"host: db.internal\napi_key: {_SECRET_KEY}\nport: 5432\nname: application\n"
_PEM = (
    "id: 1\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA1234567890abcdef\n"
    "ZZZZ1234567890abcdefMIIEowIBAAK\n-----END RSA PRIVATE KEY-----\nend: 1\n"
)


class TestRaiseIfMaskedWriteback:
    def test_whole_view_written_back_is_rejected(self) -> None:
        with pytest.raises(ToolError) as exc_info:
            raise_if_masked_writeback("/w/.env", _ENV, redact_sensitive_text(_ENV))
        assert exc_info.value.error_code == "MASKED_VALUE_WRITEBACK"

    def test_partly_masked_value_with_head_and_tail_is_rejected(self) -> None:
        masked_view = redact_sensitive_text(_YAML)
        assert "sk-pro...7890" in masked_view
        with pytest.raises(ToolError):
            raise_if_masked_writeback("/w/c.yaml", _YAML, masked_view.replace("5432", "5433"))

    def test_collapsed_private_key_block_is_rejected(self) -> None:
        with pytest.raises(ToolError):
            raise_if_masked_writeback("/w/k.yaml", _PEM, redact_sensitive_text(_PEM))

    def test_masked_line_copied_into_a_second_place_is_rejected(self) -> None:
        with pytest.raises(ToolError):
            raise_if_masked_writeback("/w/.env", _ENV, _ENV + "DB_PASSWORD=***\n")

    def test_masked_line_copied_with_other_indentation_is_rejected(self) -> None:
        disk = "db:\n    password: hunter2hunter2xyz\n"
        with pytest.raises(ToolError):
            raise_if_masked_writeback("/w/c.yaml", disk, "db:\n  password: ***\n")

    def test_error_names_the_path_and_never_the_secret(self) -> None:
        with pytest.raises(ToolError) as exc_info:
            raise_if_masked_writeback("/w/.env", _ENV, redact_sensitive_text(_ENV))
        assert "/w/.env" in str(exc_info.value)
        assert "hunter2hunter2xyz" not in exc_info.value.format_for_llm()

    @pytest.mark.parametrize(
        ("disk", "new"),
        [
            pytest.param(_ENV, _ENV.replace("5432", "5433"), id="unrelated-edit"),
            pytest.param(
                _ENV, _ENV.replace("hunter2hunter2xyz", "brandNewSecret9988"), id="secret-rotated-to-real-value"
            ),
            pytest.param("a=1\nb=2\n", "a=1\nb=3\n***\n", id="file-without-secrets"),
            pytest.param(_ENV, _ENV.replace("NAME=app", "NAME=app\nNOTE=done"), id="line-added"),
            pytest.param(_PEM, _PEM.replace("end: 1", "end: 2"), id="unrelated-edit-beside-private-key"),
            pytest.param("DB_PASSWORD=***\n", "DB_PASSWORD=***\nPORT=1\n", id="mask-already-on-disk"),
            pytest.param(_YAML, _YAML + "args: [...rest]\n", id="spread-in-file-with-a-head-tail-mask"),
            pytest.param(_ENV, _ENV + "BACKUP_PASSWORD=***\n", id="placeholder-under-another-key"),
            pytest.param(_ENV, _ENV + "NOTE=***bold***\n", id="markdown-emphasis-in-file-with-a-mask"),
        ],
    )
    def test_edits_that_carry_no_new_mask_pass(self, disk: str, new: str) -> None:
        raise_if_masked_writeback("/w/f", disk, new)


def _strategy(disk: str, *, exists: bool = True) -> AsyncMock:
    strategy = AsyncMock()
    strategy.exists = AsyncMock(return_value=exists)
    strategy.read_file = AsyncMock(return_value=disk.splitlines())
    return strategy


async def _execute(context: OperationContext, strategy: AsyncMock) -> None:
    """Run the real service, with the file system and the validators replaced, over a strategy holding the disk."""
    service = FileOperationService(context)
    with ExitStack() as stack:
        stack.enter_context(patch.object(context, "validate"))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.path_utils.resolve_file_id_path",
                return_value=context.path,
            )
        )
        stack.enter_context(patch(f"{_SERVICE}.FileSystemStrategyFactory.create_strategy", return_value=strategy))
        stack.enter_context(patch(f"{_SERVICE}.ValidatorChain")).return_value.validate = AsyncMock()
        stack.enter_context(patch(f"{_SERVICE}.get_file_integrity_guard", return_value=None))
        stack.enter_context(patch(f"{_SERVICE}.check_conflict_pre_write", return_value=None))
        stack.enter_context(
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.validators.delta_syntax_validator.DeltaSyntaxValidator.validate"
            )
        )
        for name in ("notify_file_modified", "notify_file_created"):
            stack.enter_context(patch.object(service.observer_manager, name, new_callable=AsyncMock))
        await service.execute()


def _edit(path: str, old_str: str, new_str: str) -> OperationContext:
    return OperationContext(
        operation=OperationType.STR_REPLACE,
        path=path,
        edits=(StrReplaceEdit(old_str=old_str, new_str=new_str),),
        executor=None,
    )


def _create(path: str, file_text: str) -> OperationContext:
    return OperationContext(operation=OperationType.CREATE, path=path, file_text=file_text, executor=None)


@pytest.mark.asyncio
class TestServiceRefusesMaskedWriteback:
    async def test_block_anchored_edit_copied_from_the_view_does_not_reach_disk(self) -> None:
        view = redact_sensitive_text(_YAML).rstrip("\n")
        strategy = _strategy(_YAML)
        with pytest.raises(ToolError) as exc_info:
            await _execute(_edit("/w/c.yaml", view, view.replace("5432", "5433")), strategy)
        assert exc_info.value.error_code == "MASKED_VALUE_WRITEBACK"
        strategy.write_file.assert_not_awaited()

    async def test_create_over_an_existing_file_with_its_view_does_not_reach_disk(self) -> None:
        strategy = _strategy(_ENV)
        with pytest.raises(ToolError) as exc_info:
            await _execute(_create("/w/.env", redact_sensitive_text(_ENV)), strategy)
        assert exc_info.value.error_code == "MASKED_VALUE_WRITEBACK"
        strategy.write_file.assert_not_awaited()

    async def test_exact_edit_of_an_unmasked_line_still_writes_the_real_secret(self) -> None:
        strategy = _strategy(_ENV)
        await _execute(_edit("/w/.env", "PORT=5432", "PORT=5433"), strategy)
        assert strategy.write_file.await_args.args[1] == _ENV.replace("5432", "5433").rstrip("\n")

    async def test_create_of_a_new_file_may_hold_any_text(self) -> None:
        strategy = _strategy("", exists=False)
        await _execute(_create("/w/notes.md", "password: ***\n"), strategy)
        strategy.write_file.assert_awaited_once()
