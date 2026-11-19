"""The ToolError a failed bash call hands to the model: its message, the fix hint and the error category.

[INPUT]
- .._executor.error::BashExecutionError (POS: Shared error type for BashExecutor mixins and bash_code_execute_tool error surfacing)
- .evicted_emit::emit_failure_evicted_refs (POS: announces the streams a failed call stored in full)
- .terminal_hints::annotate_failure (POS: output-pattern diagnosis appended to the hint)
- utils.errors::ToolError (POS: structured tool error the model reads)

[OUTPUT]
- build_failure_error: The ToolError for an exception raised while a bash call ran

[POS]
Failure half of ``bash_code_execute_tool``: the facade re-raises a ``ToolError`` as it is and passes any other exception here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from myrm_agent_harness.utils.errors import ToolError


async def build_failure_error(error: Exception, *, command: str, config: RunnableConfig) -> ToolError:
    """Build the ToolError for ``error``; a ``BashExecutionError`` also contributes its hint, category and stored streams."""
    from myrm_agent_harness.agent.meta_tools.bash._executor.error import BashExecutionError
    from myrm_agent_harness.agent.meta_tools.bash._tool.evicted_emit import emit_failure_evicted_refs
    from myrm_agent_harness.agent.meta_tools.bash._tool.terminal_hints import annotate_failure
    from myrm_agent_harness.utils.errors import ToolError

    hint: str | None = None
    diagnostic: dict[str, object] | None = None

    if isinstance(error, BashExecutionError):
        hint = error.error_hint
        if error.error_category:
            diagnostic = {"error_category": error.error_category}

        await emit_failure_evicted_refs(error, config=config)

        auto_hint = annotate_failure(command, 1, str(error))
        if auto_hint:
            hint = f"{hint}\n\n[Diagnostic Hint] {auto_hint}" if hint else f"[Diagnostic Hint] {auto_hint}"

    return ToolError(
        message=str(error),
        user_hint=hint or "Please fix the code and try again.",
        diagnostic_info=diagnostic,
    )


__all__ = ["build_failure_error"]
