"""Shared builder of the FileOperationService tests: a STR_REPLACE operation context."""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import (
    OperationContext,
    OperationType,
    StrReplaceEdit,
)


def str_replace_ctx(
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
