"""Integration: harness background spawn → server finish handler → chat DB."""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.api.hooks import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash.session_spawn_lifecycle import (
    reset_deferred_activation_for_tests,
)
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
    create_bash_code_execute_tool,
)
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
    BASH_PROCESS_TOOL_NAME,
)
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
    bind_workspace_storage_root,
)
from myrm_agent_harness.api.hooks import set_global_background_job_finish_handler

from app.database.models.chat import Chat
from app.platform_utils import get_session_factory
from app.services.agent.background_job_finish_handler import (
    ServerBackgroundJobFinishHandler,
)
from app.services.chat.chat_service import ChatService


def _make_local_executor(workspace: Path) -> object:
    from unittest.mock import patch as mock_patch

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
        SandboxStatus(enabled=False, provider_name="null", reason="test"),
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


async def _create_chat(chat_id: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="Background finish integration",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


@pytest.fixture(autouse=True)
def _stop_sandbox_patches() -> None:
    yield
    import unittest.mock

    unittest.mock.patch.stopall()


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    registry = get_background_registry()
    registry._entries.clear()  # type: ignore[attr-defined]
    reset_deferred_activation_for_tests()
    set_global_background_job_finish_handler(None)
    yield
    registry._entries.clear()  # type: ignore[attr-defined]
    reset_deferred_activation_for_tests()
    set_global_background_job_finish_handler(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_background_exit_persists_finish_message_to_chat(tmp_path: Path) -> None:
    """Full chain: spawn → natural exit → ServerBackgroundJobFinishHandler → ChatService."""
    chat_id = f"bg-finish-{uuid.uuid4().hex[:12]}"
    await _create_chat(chat_id)

    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())

    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }

    spawn_cmd = f"{sys.executable} -c \"print('BG_FINISH_OK')\""
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
                "command": spawn_cmd,
                "reason": "integration finish chain",
                "run_in_background": True,
            },
            config=config,
        )

    assert spawn_result["metadata"]["background"] is True
    pid = int(spawn_result["metadata"]["pid"])

    for _ in range(40):
        info = get_background_registry().get(pid)
        if info is not None and info.status == "exited":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Background process did not exit in time")

    await asyncio.sleep(0.1)

    chat = await ChatService.get_chat_by_id(chat_id)
    assert chat is not None
    bg_messages = [
        m
        for m in chat.messages
        if m.extra_data and m.extra_data.get("background_job") is True
    ]
    assert len(bg_messages) == 1
    assert str(pid) in bg_messages[0].content or "completed" in bg_messages[0].content.lower() or "已完成" in bg_messages[0].content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_background_killed_does_not_persist_finish_message(tmp_path: Path) -> None:
    """Cancel path: kill job → no chat finish message."""
    chat_id = f"bg-kill-{uuid.uuid4().hex[:12]}"
    await _create_chat(chat_id)

    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())

    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }

    long_cmd = f"{sys.executable} -c \"import time; time.sleep(60)\""
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
                "command": long_cmd,
                "reason": "integration kill chain",
                "run_in_background": True,
            },
            config=config,
        )

    pid = int(spawn_result["metadata"]["pid"])
    await get_background_registry().kill(pid, force=True)
    await asyncio.sleep(0.2)

    chat = await ChatService.get_chat_by_id(chat_id)
    assert chat is not None
    bg_messages = [
        m
        for m in chat.messages
        if m.extra_data and m.extra_data.get("background_job") is True
    ]
    assert bg_messages == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_background_nonzero_exit_persists_finish_message(tmp_path: Path) -> None:
    """Failed command still notifies GUI via chat (exit != 0)."""
    chat_id = f"bg-fail-{uuid.uuid4().hex[:12]}"
    await _create_chat(chat_id)

    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())

    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }

    fail_cmd = f"{sys.executable} -c \"import sys; sys.exit(2)\""
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
                "command": fail_cmd,
                "reason": "integration nonzero exit",
                "run_in_background": True,
            },
            config=config,
        )

    pid = int(spawn_result["metadata"]["pid"])
    for _ in range(40):
        info = get_background_registry().get(pid)
        if info is not None and info.status == "exited" and info.exit_code == 2:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Background process did not exit with code 2")

    await asyncio.sleep(0.1)
    chat = await ChatService.get_chat_by_id(chat_id)
    assert chat is not None
    bg_messages = [
        m
        for m in chat.messages
        if m.extra_data and m.extra_data.get("background_job") is True
    ]
    assert len(bg_messages) == 1
    assert bg_messages[0].extra_data.get("exit_code") == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kill_session_jobs_clears_deferred_and_skips_chat(tmp_path: Path) -> None:
    """Stream-cancel path: kill_session_jobs kills all jobs and clears AutoMount."""
    from myrm_agent_harness.agent.meta_tools.bash.session_spawn_lifecycle import (
        get_session_deferred_tool_names,
    )

    chat_id = f"bg-cancel-{uuid.uuid4().hex[:12]}"
    await _create_chat(chat_id)

    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())

    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }

    long_cmd = f"{sys.executable} -c \"import time; time.sleep(60)\""
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
        await bash_tool.ainvoke(
            {
                "command": long_cmd,
                "reason": "integration session cancel",
                "run_in_background": True,
            },
            config=config,
        )

    assert BASH_PROCESS_TOOL_NAME in get_session_deferred_tool_names(chat_id)

    killed = await get_background_registry().kill_session_jobs(chat_id, grace_seconds=0.05)
    assert killed >= 1
    await asyncio.sleep(0.2)

    assert get_session_deferred_tool_names(chat_id) == frozenset()

    chat = await ChatService.get_chat_by_id(chat_id)
    assert chat is not None
    bg_messages = [
        m
        for m in chat.messages
        if m.extra_data and m.extra_data.get("background_job") is True
    ]
    assert bg_messages == []
