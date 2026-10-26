"""The runtime context a real agent run hands to middleware and tools.

[INPUT]
- myrm_agent_harness.agent._internals.run_lifecycle::setup_workspace (POS: the production path that builds the run context)

[OUTPUT]
- real_run_context: awaitable returning the context ``setup_workspace`` produces for a workspace directory

[POS]
Harness pytest-only helper. A hand-built ``{"some_key": ...}`` context passes whatever key a
reader asks for, so a reader of a key the run never writes still goes green. Tests that must
prove a reader sees what production hands it take their context from here.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.agent._internals.run_lifecycle import setup_workspace

_LIFECYCLE = "myrm_agent_harness.agent._internals.run_lifecycle"


async def real_run_context(workspace: Path) -> dict[str, object]:
    """Run ``setup_workspace`` for ``workspace`` and return the context it builds."""
    service = MagicMock()
    service.get_or_create = AsyncMock(return_value="workspace")
    service.get_workspace_absolute_path.return_value = str(workspace)
    with (
        patch(f"{_LIFECYCLE}.create_workspace_service", return_value=service),
        patch(f"{_LIFECYCLE}.set_workspace_root"),
        patch("myrm_agent_harness.toolkits.code_execution.executors.base.set_executor"),
    ):
        context, _ = await setup_workspace(
            executor=MagicMock(),
            context={"session_id": "run-context", "workspaces_storage_root": str(workspace.parent)},
        )
    return context
