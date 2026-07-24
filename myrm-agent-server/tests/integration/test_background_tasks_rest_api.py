"""Integration: REST /background-tasks ↔ harness registry (no mocks on registry path)."""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
    create_bash_code_execute_tool,
)
from myrm_agent_harness.agent.meta_tools.bash.session_spawn_lifecycle import (
    reset_spawn_lifecycle_for_tests,
)
from myrm_agent_harness.api.hooks import (
    get_background_registry,
    set_global_background_job_finish_handler,
)
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
    bind_workspace_storage_root,
)

from app.services.agent.background_job_finish_handler import (
    ServerBackgroundJobFinishHandler,
)
from tests.integration.test_background_job_finish_chain import _make_local_executor


def _build_rest_app():
    from fastapi import FastAPI

    from app.api.background_tasks.router import router as background_tasks_router

    app = FastAPI()
    app.include_router(background_tasks_router, prefix="/api/v1/background-tasks")
    return app


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    registry = get_background_registry()
    registry._entries.clear()  # type: ignore[attr-defined]
    reset_spawn_lifecycle_for_tests()
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())
    yield
    registry._entries.clear()  # type: ignore[attr-defined]
    reset_spawn_lifecycle_for_tests()
    set_global_background_job_finish_handler(None)


async def _spawn_background(
    tmp_path: Path,
    *,
    chat_id: str,
    command: str,
    reason: str,
) -> tuple[int, str]:
    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }
    bash_tool = create_bash_code_execute_tool()
    with (
        patch(
            "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
            AsyncMock(),
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
                "reason": reason,
                "run_in_background": True,
            },
            config=config,
        )
    return int(spawn_result["metadata"]["pid"]), str(spawn_result["metadata"]["job_id"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_list_and_get_shell_task(tmp_path: Path) -> None:
    chat_id = f"rest-list-{uuid.uuid4().hex[:12]}"
    sleep_cmd = f'{sys.executable} -c "import time; time.sleep(30)"'
    pid, job_id = await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=sleep_cmd,
        reason="rest list integration",
    )

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        list_resp = await client.get("/api/v1/background-tasks")
        assert list_resp.status_code == 200
        list_payload = list_resp.json()
        assert list_payload.get("registry_ephemeral") is False
        tasks = list_payload["tasks"]
        shell_rows = [
            t for t in tasks if t.get("kind") == "shell" and t.get("pid") == pid
        ]
        assert len(shell_rows) == 1
        row = shell_rows[0]
        assert row["task_id"] == f"shell:{row['job_id']}"
        assert row["status"] == "running"
        assert row["chat_id"] == chat_id

        get_resp = await client.get(f"/api/v1/background-tasks/shell:{job_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["pid"] == pid
        assert get_resp.json()["job_id"] == job_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_cancel_shell_task(tmp_path: Path) -> None:
    chat_id = f"rest-cancel-{uuid.uuid4().hex[:12]}"
    long_cmd = f'{sys.executable} -c "import time; time.sleep(60)"'
    pid, job_id = await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=long_cmd,
        reason="rest cancel integration",
    )

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        cancel_resp = await client.post(
            f"/api/v1/background-tasks/shell:{job_id}/cancel"
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["task_id"] == f"shell:{job_id}"

    await asyncio.sleep(0.15)
    info = get_background_registry().get(pid)
    assert info is not None
    assert info.status == "killed"

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        list_resp = await client.get("/api/v1/background-tasks")
        shell_rows = [
            t
            for t in list_resp.json()["tasks"]
            if t.get("kind") == "shell" and t.get("pid") == pid
        ]
        assert shell_rows
        assert shell_rows[0]["status"] == "cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_steer_rejected() -> None:
    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/background-tasks/shell:99999/steer",
            json={"instruction": "noop"},
        )
    assert resp.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_invalid_shell_id_returns_404() -> None:
    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (
            await client.get("/api/v1/background-tasks/shell:not-a-pid")
        ).status_code == 404
        assert (
            await client.get("/api/v1/background-tasks/shell:99999999")
        ).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_failed_task_exposes_exit_metadata(tmp_path: Path) -> None:
    chat_id = f"rest-fail-{uuid.uuid4().hex[:12]}"
    fail_cmd = f'{sys.executable} -c "import sys; sys.exit(42)"'
    pid, job_id = await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=fail_cmd,
        reason="rest fail integration",
    )

    for _ in range(30):
        info = get_background_registry().get(pid)
        if info is not None and info.status == "exited":
            break
        await asyncio.sleep(0.05)

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_resp = await client.get(f"/api/v1/background-tasks/shell:{job_id}")
        assert get_resp.status_code == 200
        row = get_resp.json()
        assert row["status"] == "failed"
        assert row["exit_code"] == 42
        assert row["error_category"] == "nonzero_exit"


def _stdin_echo_cmd() -> str:
    return (
        f"{sys.executable} -c "
        '"import sys,time; line=sys.stdin.readline(); '
        "print('MYRM_STDIN_ECHO:'+line.strip(), flush=True); time.sleep(30)\""
    )


async def _wait_stdout_tail_contains(
    pid: int, needle: str, *, timeout_sec: float = 10.0
) -> None:
    import time as time_mod

    deadline = time_mod.monotonic() + timeout_sec
    while time_mod.monotonic() < deadline:
        info = get_background_registry().get(pid)
        if info is not None:
            tail = info.last_stdout_tail or []
            if any(needle in line for line in tail):
                return
        await asyncio.sleep(0.1)
    raise AssertionError(f"stdout tail never contained {needle!r} for pid={pid}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_stdin_write_echo(tmp_path: Path) -> None:
    chat_id = f"rest-stdin-{uuid.uuid4().hex[:12]}"
    pid, job_id = await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=_stdin_echo_cmd(),
        reason="rest stdin integration echo",
    )
    task_id = f"shell:{job_id}"

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        stdin_resp = await client.post(
            f"/api/v1/background-tasks/{task_id}/stdin",
            json={"data": "hello", "submit": True},
        )
        assert stdin_resp.status_code == 200
        payload = stdin_resp.json()
        assert payload["task_id"] == task_id
        assert payload["result"]["ok"] is True

    await _wait_stdout_tail_contains(pid, "MYRM_STDIN_ECHO:hello")

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        list_resp = await client.get("/api/v1/background-tasks")
        shell_rows = [
            t
            for t in list_resp.json()["tasks"]
            if t.get("kind") == "shell" and t.get("pid") == pid
        ]
        assert shell_rows
        preview = shell_rows[0].get("result_preview") or ""
        assert "MYRM_STDIN_ECHO:hello" in preview

        await client.post(f"/api/v1/background-tasks/{task_id}/cancel")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_stdin_rejects_non_shell_task() -> None:
    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/background-tasks/agent:fake-job/stdin",
            json={"data": "x"},
        )
    assert resp.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_stdin_rejects_exited_task(tmp_path: Path) -> None:
    chat_id = f"rest-stdin-exit-{uuid.uuid4().hex[:12]}"
    pid, job_id = await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=f'{sys.executable} -c "print(1)"',
        reason="rest stdin exited integration",
    )
    task_id = f"shell:{job_id}"

    for _ in range(30):
        info = get_background_registry().get(pid)
        if info is not None and info.status == "exited":
            break
        await asyncio.sleep(0.05)

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            f"/api/v1/background-tasks/{task_id}/stdin",
            json={"data": "late"},
        )
    assert resp.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_stdin_404_unknown_task() -> None:
    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/background-tasks/shell:99999999/stdin",
            json={"data": "x"},
        )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_shell_stdin_close_eof(tmp_path: Path) -> None:
    chat_id = f"rest-stdin-close-{uuid.uuid4().hex[:12]}"
    close_cmd = (
        f"{sys.executable} -c "
        '"import sys; data=sys.stdin.read(); '
        "print('MYRM_STDIN_CLOSED:'+str(len(data)), flush=True); "
        'import time; time.sleep(5)"'
    )
    pid, job_id = await _spawn_background(
        tmp_path,
        chat_id=chat_id,
        command=close_cmd,
        reason="rest stdin close integration",
    )
    task_id = f"shell:{job_id}"

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        stdin_resp = await client.post(
            f"/api/v1/background-tasks/{task_id}/stdin",
            json={"data": "partial", "submit": False, "close": True},
        )
        assert stdin_resp.status_code == 200
        assert stdin_resp.json()["result"]["ok"] is True

    await _wait_stdout_tail_contains(pid, "MYRM_STDIN_CLOSED:7")
