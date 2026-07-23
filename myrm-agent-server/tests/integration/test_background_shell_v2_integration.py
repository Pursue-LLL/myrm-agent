"""Integration: Background Shell Runtime v2.1 end-to-end harness + REST paths."""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.agent.meta_tools.bash.session_spawn_lifecycle import reset_spawn_lifecycle_for_tests
from myrm_agent_harness.api.hooks import (
    count_running_background_shell_jobs,
    get_background_registry,
    set_global_background_job_finish_handler,
)
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import bind_workspace_storage_root

from app.services.agent.background_job_finish_handler import ServerBackgroundJobFinishHandler
from tests.integration.test_background_job_finish_chain import _make_local_executor
from tests.integration.test_background_tasks_rest_api import _build_rest_app, _spawn_background


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


def _session_config(chat_id: str, tmp_path: Path) -> dict[str, object]:
    return {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bash_process_wait_and_poll_hint_integration(tmp_path: Path) -> None:
    chat_id = f"v2-wait-{uuid.uuid4().hex[:12]}"
    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    config = _session_config(chat_id, tmp_path)

    bash_tool = create_bash_code_execute_tool()
    process_tool = create_bash_process_tool()
    cmd = f'{sys.executable} -c "import time; print(\'tick\', flush=True); time.sleep(0.4)"'

    with (
        patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()),
        patch(
            "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)),
        ),
    ):
        spawn = await bash_tool.ainvoke(
            {"command": cmd, "reason": "wait integration", "run_in_background": True},
            config=config,
        )

    pid = int(spawn["metadata"]["pid"])
    out1 = await process_tool.ainvoke({"action": "output", "pid": pid}, config=config)
    cursor = int(out1["content"]["next_cursor"])  # type: ignore[index]
    out2 = await process_tool.ainvoke(
        {"action": "output", "pid": pid, "since_cursor": cursor},
        config=config,
    )
    hint = out2["content"]["poll_hint"]  # type: ignore[index]
    assert hint["has_new_output"] is False
    assert hint["suggested_wait_ms"] >= 5000

    wait_result = await process_tool.ainvoke(
        {"action": "wait", "pid": pid, "timeout_seconds": 5},
        config=config,
    )
    assert wait_result["metadata"]["still_running"] is False
    assert wait_result["content"]["exit_code"] == 0  # type: ignore[index]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auto_yield_whitelist_command(tmp_path: Path) -> None:
    chat_id = f"v2-yield-{uuid.uuid4().hex[:12]}"
    slow_test = tmp_path / "slow_test.py"
    slow_test.write_text("import time\n\ndef test_slow():\n    time.sleep(5)\n", encoding="utf-8")

    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    config = _session_config(chat_id, tmp_path)
    bash_tool = create_bash_code_execute_tool()

    with (
        patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()),
        patch(
            "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)),
        ),
    ):
        result = await bash_tool.ainvoke(
            {
                "command": f"pytest -q {slow_test}::test_slow",
                "reason": "auto yield integration",
                "yield_after_seconds": 1,
            },
            config=config,
        )

    assert result["metadata"].get("auto_yielded") is True
    assert result["metadata"].get("background") is True or result["metadata"].get("completed_in_yield_window") is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_preview_redacts_secrets(tmp_path: Path) -> None:
    chat_id = f"v2-redact-{uuid.uuid4().hex[:12]}"
    secret = "sk-live-abcdefghijklmnopqrstuvwxyz"
    cmd = f'{sys.executable} -c "print(\'{secret}\', flush=True)"'
    pid, job_id = await _spawn_background(tmp_path, chat_id=chat_id, command=cmd, reason="redact integration")

    for _ in range(30):
        preview_source = get_background_registry().get(pid)
        if preview_source and preview_source.last_stdout_tail:
            break
        await asyncio.sleep(0.05)

    transport = ASGITransport(app=_build_rest_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        row = (await client.get(f"/api/v1/background-tasks/shell:{job_id}")).json()

    assert secret not in str(row.get("result_preview", ""))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_finish_handler_dedupe_integration() -> None:
    from myrm_agent_harness.api.hooks import BackgroundJobFinishResult

    handler = ServerBackgroundJobFinishHandler()
    result = BackgroundJobFinishResult(
        session_id="chat-dedupe-int",
        job_id="f" * 32,
        pid=12345,
        command="pytest -q",
        status="exited",
        exit_code=0,
        error_category=None,
    )

    with (
        patch(
            "app.services.agent.background_job_finish_handler._resolve_user_locale",
            AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.agent.background_job_finish_handler.ChatService.append_message",
            AsyncMock(),
        ) as mock_append,
        patch(
            "app.services.agent.background_job_finish_handler.get_event_bus",
            return_value=AsyncMock(),
        ),
        patch(
            "app.services.agent.goal_wait_background_resume.maybe_resume_goal_after_background_job",
            AsyncMock(),
        ),
    ):
        await handler.on_background_job_finish(result)
        await handler.on_background_job_finish(result)

    mock_append.assert_awaited_once()
    assert ("chat-dedupe-int", "f" * 32) in handler._processed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_running_hook_matches_registry(tmp_path: Path) -> None:
    chat_id = f"v2-count-{uuid.uuid4().hex[:12]}"
    sleep_cmd = f'{sys.executable} -c "import time; time.sleep(30)"'
    await _spawn_background(tmp_path, chat_id=chat_id, command=sleep_cmd, reason="count hook")
    assert count_running_background_shell_jobs() >= 1
    assert count_running_background_shell_jobs() == get_background_registry().count_running()
