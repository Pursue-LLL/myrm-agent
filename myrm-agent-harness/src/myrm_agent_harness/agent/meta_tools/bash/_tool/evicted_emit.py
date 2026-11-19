"""Tell the UI which stream of a bash call was stored in full, so it can offer the stored output.

[INPUT]
- agent.context_management.infra.evicted::emit_evicted_ref (POS: announces one stored stream to the UI; imported when a stream was stored)
- .._executor.error::BashExecutionError (POS: Shared error type for BashExecutor mixins and bash_code_execute_tool error surfacing; type only)

[OUTPUT]
- emit_result_evicted_refs: Announce the streams a finished call stored in full (stdout with the preview the model got, then stderr)
- emit_failure_evicted_refs: Announce the streams a failed call stored in full, one failed announcement never masking the error

[POS]
Eviction announcements of ``bash_code_execute_tool``: the executor stores a large stream and records its reference; this module sends the reference to the UI on both the success and the failure path.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError

logger = logging.getLogger(__name__)

_TOOL_NAME = "bash_code_execute_tool"


def _coerce_optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


async def emit_result_evicted_refs(
    result: Mapping[str, object],
    *,
    formatted_content: str,
    config: RunnableConfig,
) -> None:
    """Announce the streams of a finished call that were stored in full."""
    evicted_ref = result.get("evicted_ref")
    if evicted_ref and isinstance(evicted_ref, str):
        from myrm_agent_harness.agent.context_management.infra.evicted import (
            emit_evicted_ref,
        )

        await emit_evicted_ref(
            evicted_ref,
            tool_name=_TOOL_NAME,
            preview_stdout=formatted_content,
            stored_chars=_coerce_optional_int(result.get("evicted_stored_chars")),
            total_lines=_coerce_optional_int(result.get("evicted_total_lines")),
            storage_truncated=bool(result.get("evicted_storage_truncated")),
            stream="stdout",
            config=config,
        )

    stderr_evicted_ref = result.get("stderr_evicted_ref")
    if stderr_evicted_ref and isinstance(stderr_evicted_ref, str):
        from myrm_agent_harness.agent.context_management.infra.evicted import (
            emit_evicted_ref,
        )

        await emit_evicted_ref(
            stderr_evicted_ref,
            tool_name=_TOOL_NAME,
            stored_chars=_coerce_optional_int(result.get("stderr_evicted_stored_chars")),
            total_lines=_coerce_optional_int(result.get("stderr_evicted_total_lines")),
            storage_truncated=bool(result.get("stderr_evicted_storage_truncated")),
            stream="stderr",
            config=config,
        )


async def emit_failure_evicted_refs(error: BashExecutionError, *, config: RunnableConfig) -> None:
    """Announce the streams of a failed call that were stored in full."""
    if not (error.stdout_evicted_ref or error.stderr_evicted_ref):
        return

    from myrm_agent_harness.agent.context_management.infra.evicted import (
        emit_evicted_ref,
    )

    async def _emit_evicted(
        ref: str,
        *,
        stream: str,
        stored_chars: int | None,
        total_lines: int | None,
        storage_truncated: bool,
    ) -> None:
        try:
            await emit_evicted_ref(
                ref,
                tool_name=_TOOL_NAME,
                stored_chars=stored_chars,
                total_lines=total_lines,
                storage_truncated=storage_truncated,
                stream=stream,
                config=config,
            )
        except Exception as emit_exc:
            logger.warning(
                "Failed to emit %s evicted ref %s: %s",
                stream,
                ref,
                emit_exc,
            )

    # Failure path intentionally omits preview_stdout: step.stdout
    # keeps the partial output accumulated during execution (the
    # "how far did it get" context), while the drawer still exposes
    # the full evicted stream for read-back.
    if error.stdout_evicted_ref:
        await _emit_evicted(
            error.stdout_evicted_ref,
            stream="stdout",
            stored_chars=error.stdout_evicted_stored_chars,
            total_lines=error.stdout_evicted_total_lines,
            storage_truncated=error.stdout_evicted_storage_truncated,
        )
    if error.stderr_evicted_ref:
        await _emit_evicted(
            error.stderr_evicted_ref,
            stream="stderr",
            stored_chars=error.stderr_evicted_stored_chars,
            total_lines=error.stderr_evicted_total_lines,
            storage_truncated=error.stderr_evicted_storage_truncated,
        )


__all__ = ["emit_failure_evicted_refs", "emit_result_evicted_refs"]
