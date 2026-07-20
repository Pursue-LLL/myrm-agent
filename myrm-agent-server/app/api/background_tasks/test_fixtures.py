"""Local-only HTTP fixtures for Background Tasks Chrome E2E.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: local-only route guard)
- myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool::create_bash_code_execute_tool (POS: bash spawn)

[OUTPUT]
- seed_shell_fixture: spawn a real harness background shell job on the live server registry

[POS]
Background tasks API local test fixture. Enables Chrome E2E to assert panel rows without LLM.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, patch

from fastapi import APIRouter, HTTPException, Query

from app.config.deploy_mode import is_local_mode
from app.config.settings import get_settings

router = APIRouter()


def _make_local_executor(workspace: Path) -> object:
    from unittest.mock import patch as mock_patch

    from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
    from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus

    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(workspace))
    null_result = (
        NullProvider(),
        SandboxStatus(enabled=False, provider_name="null", reason="e2e-fixture"),
    )
    mock_patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
        return_value=null_result,
    ).start()
    mock_patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        return_value=null_result,
    ).start()
    return executor


async def _spawn_shell_fixture(
    *,
    workspace: Path,
    chat_id: str,
    command: str,
) -> int:
    from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
    from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
    from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import bind_workspace_storage_root

    workspace.mkdir(parents=True, exist_ok=True)
    executor = _make_local_executor(workspace)
    set_executor(executor)
    bind_workspace_storage_root(workspace)

    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(workspace),
                "workspaces_storage_root": str(workspace),
            }
        }
    }
    bash_tool = create_bash_code_execute_tool()
    with (
        patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()),
        patch(
            "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
    ):
        spawn_result = await bash_tool.ainvoke(
            {
                "command": command,
                "reason": "background tasks chrome e2e seed",
                "run_in_background": True,
            },
            config=config,
        )
    return int(spawn_result["metadata"]["pid"])


@router.post("/test/seed-shell-fixture", include_in_schema=False)
async def seed_shell_fixture(
    mode: Literal["failed", "running"] = Query(default="failed"),
) -> dict[str, object]:
    """Local dev/test only: seed a shell background job for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2e-shell-{uuid.uuid4().hex[:10]}"
    settings = get_settings()
    workspace = Path(settings.database.state_dir).expanduser() / "e2e-fixtures" / chat_id

    if mode == "running":
        command = (
            f'{sys.executable} -c "import time; print(\'MYRM_E2E_SHELL_RUNNING\', flush=True); time.sleep(120)"'
        )
    else:
        command = f'{sys.executable} -c "import sys; sys.exit(42)"'

    pid = await _spawn_shell_fixture(workspace=workspace, chat_id=chat_id, command=command)
    from myrm_agent_harness.api.hooks import get_background_registry

    if mode == "failed":
        registry = get_background_registry()
        for _ in range(40):
            info = registry.get(pid)
            if info is not None and info.status == "exited":
                break
            await asyncio.sleep(0.05)

    info = get_background_registry().get(pid)
    job_id = info.job_id if info is not None else str(pid)

    return {
        "chat_id": chat_id,
        "pid": pid,
        "job_id": job_id,
        "task_id": f"shell:{job_id}",
        "mode": mode,
    }
