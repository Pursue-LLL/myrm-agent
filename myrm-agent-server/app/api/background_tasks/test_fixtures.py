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
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, patch

from fastapi import APIRouter, HTTPException, Query

from app.config.deploy_mode import is_local_mode
from app.config.settings import get_settings
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_VAULT_SPILL_LINE_COUNT = 85
_SUCCESS_MARKER = "MYRM_E2E_SHELL_SUCCESS"


def _make_local_executor(workspace: Path) -> object:
    from unittest.mock import patch as mock_patch

    from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
    from myrm_agent_harness.toolkits.code_execution.executors.local.executor import (
        LocalExecutor,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import (
        NullProvider,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
        SandboxStatus,
    )

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
    from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
        create_bash_code_execute_tool,
    )
    from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
    from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
        bind_workspace_storage_root,
    )

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
        patch(
            "myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()
        ),
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


async def _ensure_e2e_chat(chat_id: str) -> None:
    agents, _total = await AgentService.get_agent_list(1, 100)
    agent_id = agents[0].id if agents else None
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Background shell Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )


async def _wait_registry_pid(
    pid: int,
    *,
    want_status: str,
    timeout_sec: float = 12.0,
) -> object | None:
    from myrm_agent_harness.api.hooks import get_background_registry

    registry = get_background_registry()
    deadline = time.monotonic() + timeout_sec
    info: object | None = None
    while time.monotonic() < deadline:
        info = registry.get(pid)
        if info is not None and getattr(info, "status", None) == want_status:
            return info
        await asyncio.sleep(0.05)
    return registry.get(pid)


async def _wait_vault_log_ref(pid: int, timeout_sec: float = 15.0) -> str | None:
    from myrm_agent_harness.api.hooks import get_background_registry

    registry = get_background_registry()
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        info = registry.get(pid)
        ref = getattr(info, "vault_log_ref", None) if info is not None else None
        if ref:
            return str(ref)
        await asyncio.sleep(0.05)
    info = registry.get(pid)
    if info is None:
        return None
    ref = getattr(info, "vault_log_ref", None)
    return str(ref) if ref else None


def _resolve_evicted_workspace_root(workspace: Path) -> Path:
    workspace_env = os.environ.get("MYRM_WORKSPACE_ROOT")
    if workspace_env:
        candidate = Path(workspace_env).expanduser()
        if candidate.is_dir():
            return candidate
    try:
        from myrm_agent_harness.toolkits.code_execution.workspace.registry import (
            get_active_workspace_path,
        )

        active = get_active_workspace_path()
        if active:
            return Path(active)
    except Exception:
        pass
    if is_local_mode():
        default = Path.home() / ".myrm" / "workspace"
        if default.is_dir():
            return default
    return workspace


def _write_vault_log_fixture(*, chat_id: str, pid: int, workspace: Path) -> str:
    """Ensure a real evicted spill file exists for Chrome E2E vault drawer tests."""
    from myrm_agent_harness.api.hooks import (
        BackgroundProcessInfo,
        get_background_job_store,
        get_background_registry,
        persist_terminal_state,
        persist_vault_log_ref,
    )

    filename = f"output_{uuid.uuid4().hex[:8]}.txt"
    content = "".join(
        f"MYRM_E2E_VAULT_LINE_{index}\n" for index in range(_VAULT_SPILL_LINE_COUNT)
    )

    write_roots = [workspace]
    server_root = _resolve_evicted_workspace_root(workspace)
    if server_root not in write_roots:
        write_roots.append(server_root)

    for root in write_roots:
        evicted_dir = root / ".context" / chat_id / "evicted"
        evicted_dir.mkdir(parents=True, exist_ok=True)
        (evicted_dir / filename).write_text(content, encoding="utf-8")

    registry = get_background_registry()
    live_info: BackgroundProcessInfo | None = None
    with registry._lock:  # noqa: SLF001 — E2E fixture must mutate live registry, not get() snapshot
        entry = registry._entries.get(pid)  # noqa: SLF001
        if entry is not None:
            entry.info.vault_log_ref = filename
            live_info = registry._snapshot(entry)  # noqa: SLF001

    if live_info is not None:
        persist_vault_log_ref(live_info)
        persist_terminal_state(live_info)
        return filename

    store = get_background_job_store()
    if store is not None:
        record = store.get_by_pid(pid)
        if record is not None:
            store.set_vault_log_ref(record.job_id, filename)
            synthetic = BackgroundProcessInfo(
                job_id=record.job_id,
                pid=pid,
                command=record.command,
                session_id=record.session_id,
                started_at=record.started_at,
                status=record.status if record.status != "orphaned" else "exited",
                exit_code=record.exit_code,
                error_category=record.error_category,
                vault_log_ref=filename,
            )
            persist_terminal_state(synthetic)
    return filename


@router.post("/test/seed-shell-fixture", include_in_schema=False)
async def seed_shell_fixture(
    mode: Literal[
        "failed", "running", "running_stdin", "success", "completed_with_vault"
    ] = Query(default="failed"),
) -> dict[str, object]:
    """Local dev/test only: seed a shell background job for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2e-shell-{uuid.uuid4().hex[:10]}"
    if mode in {"success", "completed_with_vault"}:
        await _ensure_e2e_chat(chat_id)

    settings = get_settings()
    workspace = (
        Path(settings.database.state_dir).expanduser() / "e2e-fixtures" / chat_id
    )

    if mode == "running":
        command = f"{sys.executable} -c \"import time; print('MYRM_E2E_SHELL_RUNNING', flush=True); time.sleep(120)\""
    elif mode == "running_stdin":
        command = (
            f"{sys.executable} -c "
            '"import sys,time; line=sys.stdin.readline(); '
            "print('MYRM_STDIN_ECHO:'+line.strip(), flush=True); time.sleep(120)\""
        )
    elif mode == "success":
        command = f"{sys.executable} -c \"print('{_SUCCESS_MARKER}', flush=True)\""
    elif mode == "completed_with_vault":
        command = f"{sys.executable} -c \"print('MYRM_E2E_VAULT_DONE', flush=True)\""
    else:
        command = f'{sys.executable} -c "import sys; sys.exit(42)"'

    pid = await _spawn_shell_fixture(
        workspace=workspace, chat_id=chat_id, command=command
    )
    from myrm_agent_harness.api.hooks import get_background_registry

    if mode in {"failed", "success", "completed_with_vault"}:
        await _wait_registry_pid(pid, want_status="exited")

    vault_log_ref: str | None = None
    if mode == "completed_with_vault":
        vault_log_ref = await _wait_vault_log_ref(pid, timeout_sec=2.0)
        if not vault_log_ref:
            vault_log_ref = _write_vault_log_fixture(
                chat_id=chat_id, pid=pid, workspace=workspace
            )

    info = get_background_registry().get(pid)
    job_id = info.job_id if info is not None else str(pid)
    if vault_log_ref is None and info is not None:
        ref = getattr(info, "vault_log_ref", None)
        vault_log_ref = str(ref) if ref else None

    return {
        "chat_id": chat_id,
        "pid": pid,
        "job_id": job_id,
        "task_id": f"shell:{job_id}",
        "mode": mode,
        "vault_log_ref": vault_log_ref,
    }
