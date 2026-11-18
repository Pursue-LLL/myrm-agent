"""Integration: a finished background job whose result the agent already read does not wake it a second time.

The chain is real end to end: the job starts through the real bash tool, its finish goes through the real finish
handler and adaptive wakeup service, and the agent's read goes through the real ``bash_process_tool`` and wakeup
handler. The stand-ins are the sandbox and the turn the wake would stream. While the agent's own turn holds the chat the
wake turn waits, so each test ends that turn and then sees whether a wake turn started.
"""

from __future__ import annotations

import asyncio
import sys
import unittest.mock
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.api.hooks import get_background_registry, set_global_background_job_finish_handler
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import bind_workspace_storage_root
from myrm_agent_harness.utils.runtime.wakeup_registry import set_global_wakeup_handler

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service, wake_turn_scheduler
from app.services.agent.adaptive_wakeup import service as service_module
from app.services.agent.background_job.background_job_finish_handler import ServerBackgroundJobFinishHandler
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.params.workspace_resolve import chat_session_id
from app.services.agent.wakeup_handler import ServerWakeupHandler
from app.services.chat.chat_service import ChatService
from tests.integration.test_background_job_finish_chain import _create_chat, _make_local_executor

_REASON = "integration read stand-down"
_STEP_TIMEOUT_SECONDS = 15.0


@pytest.fixture(autouse=True)
def _chain() -> Iterator[None]:
    """The registry is empty, the host's two hooks are the real ones, and the tools run outside a LangGraph run."""
    registry = get_background_registry()
    registry._entries.clear()  # type: ignore[attr-defined]
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())
    set_global_wakeup_handler(ServerWakeupHandler())
    patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", AsyncMock()).start()
    patch(
        "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
        return_value=AsyncMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)),
    ).start()
    yield
    registry._entries.clear()  # type: ignore[attr-defined]
    set_global_background_job_finish_handler(None)
    set_global_wakeup_handler(None)
    unittest.mock.patch.stopall()


@pytest.fixture
def streamed(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The turn a wake would stream: the model run itself is the one thing not exercised here."""
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(service_module, "check_estop", lambda: None)
    monkeypatch.setattr(service_module, "should_block_execution", AsyncMock(return_value=False))
    stream = AsyncMock(return_value=None)
    monkeypatch.setattr(service_module, "stream_wake_turn", stream)
    return stream


@pytest.fixture
async def chat_id() -> AsyncIterator[str]:
    """A stored chat whose agent turn is running: the wake turn of a finish waits behind it."""
    chat = f"bg-read-{uuid.uuid4().hex[:12]}"
    await _create_chat(chat)
    get_agent_gateway().reserve_session(chat, active_message_id="user-turn")
    yield chat
    get_agent_gateway().release_session(chat)
    wake_turn_scheduler._waiting.pop(chat, None)
    get_adaptive_wakeup_service().forget_chat(chat)


class _Agent:
    """The model's side of one chat: the real bash tools, bound to the chat's session and a temporary workspace."""

    def __init__(self, chat_id: str, workspace: Path) -> None:
        set_executor(_make_local_executor(workspace))
        bind_workspace_storage_root(workspace)
        self.config: RunnableConfig = {
            "configurable": {
                "context": {
                    "session_id": chat_session_id(chat_id),
                    "workspace_path": str(workspace),
                    "workspaces_storage_root": str(workspace),
                }
            }
        }
        self._bash = create_bash_code_execute_tool()
        self._process = create_bash_process_tool()

    async def start_job(self, code: str) -> int:
        """Start ``python -c code`` as a background job and return its pid."""
        spawned = await self._bash.ainvoke(
            {"command": f'{sys.executable} -c "{code}"', "reason": _REASON, "run_in_background": True}, config=self.config
        )
        return int(spawned["metadata"]["pid"])

    async def run_build(self, code: str) -> dict[str, object]:
        """A foreground ``python -c code`` whose text names ``pytest``, a command the tool lets run ahead for a while."""
        return await self._bash.ainvoke({"command": f'{sys.executable} -c "{code}"', "reason": _REASON}, config=self.config)

    async def process(self, **arguments: object) -> dict[str, object]:
        return await self._process.ainvoke(arguments, config=self.config)


@pytest.fixture
def agent(chat_id: str, tmp_path: Path) -> _Agent:
    return _Agent(chat_id, tmp_path)


async def _until(predicate: Callable[[], bool], what: str) -> None:
    try:
        async with asyncio.timeout(_STEP_TIMEOUT_SECONDS):
            while not predicate():
                await asyncio.sleep(0.02)
    except TimeoutError:
        pytest.fail(f"Timed out waiting for {what}")


def _wake_queued(chat_id: str) -> Callable[[], bool]:
    return lambda: chat_id in wake_turn_scheduler._waiting


def _settlements_queued(chat_id: str, count: int) -> Callable[[], bool]:
    return lambda: len(get_adaptive_wakeup_service()._settled._queued.get(chat_id, ())) == count


def _exited(pid: int) -> Callable[[], bool]:
    def check() -> bool:
        job = get_background_registry().get(pid)
        return job is not None and job.status == "exited"

    return check


async def _end_the_agents_turn(chat_id: str) -> None:
    """The agent's turn ends; the wake turn queued behind it then starts or stands down."""
    get_agent_gateway().release_session(chat_id)
    async with asyncio.timeout(_STEP_TIMEOUT_SECONDS):
        while wake_turn_scheduler._tasks:
            await asyncio.gather(*list(wake_turn_scheduler._tasks))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_job_nobody_read_wakes_the_agent(agent: _Agent, chat_id: str, streamed: AsyncMock) -> None:
    """The control: without a read the finish queues a wake turn and it runs, so the cases below stand a real one down."""
    await agent.start_job("print('built')")
    await _until(_wake_queued(chat_id), "the finish to queue a wake turn")

    await _end_the_agents_turn(chat_id)

    streamed.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_wait_that_returns_the_exit_stands_the_wake_turn_down(agent: _Agent, chat_id: str, streamed: AsyncMock) -> None:
    pid = await agent.start_job("print('built')")
    await _until(_wake_queued(chat_id), "the finish to queue a wake turn")

    waited = await agent.process(action="wait", pid=pid, timeout_seconds=10)

    assert waited["content"]["exit_code"] == 0 and waited["content"]["stdout"] == ["built"]
    await _end_the_agents_turn(chat_id)
    streamed.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_output_read_of_a_finished_job_stands_the_wake_turn_down(
    agent: _Agent, chat_id: str, streamed: AsyncMock
) -> None:
    pid = await agent.start_job("print('built')")
    await _until(_wake_queued(chat_id), "the finish to queue a wake turn")

    polled = await agent.process(action="output", pid=pid)

    assert polled["content"]["exit_code"] == 0 and polled["content"]["stdout"] == ["built"]
    await _end_the_agents_turn(chat_id)
    streamed.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_listing_is_not_a_read(agent: _Agent, chat_id: str, streamed: AsyncMock) -> None:
    """A listing names the job and its state but not what it printed, so the wake turn still brings the result."""
    await agent.start_job("print('built')")
    await _until(_wake_queued(chat_id), "the finish to queue a wake turn")

    listed = await agent.process(action="list")

    assert listed["content"]["count"] == 1
    await _end_the_agents_turn(chat_id)
    streamed.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_build_command_that_ends_inside_the_window_stands_the_wake_turn_down(
    agent: _Agent, chat_id: str, streamed: AsyncMock
) -> None:
    """The command's own return held the whole result, so the finish that follows has nothing new to say."""
    returned = await agent.run_build("print('pytest ok')")

    assert "Command finished during auto-yield window" in str(returned["content"])
    assert "pytest ok" in str(returned["content"])
    await _until(_wake_queued(chat_id), "the finish to queue a wake turn")
    await _end_the_agents_turn(chat_id)
    streamed.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_job_that_is_still_unread_keeps_the_wake_turn(agent: _Agent, chat_id: str, streamed: AsyncMock) -> None:
    """Two jobs finished and the agent read one of them: the wake turn still runs for the other."""
    read = await agent.start_job("print('first')")
    await agent.start_job("print('second')")
    await _until(_settlements_queued(chat_id, 2), "both finishes to be settled")

    await agent.process(action="output", pid=read)

    await _end_the_agents_turn(chat_id)
    streamed.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_result_read_before_the_finish_is_settled_stands_the_wake_turn_down(
    agent: _Agent, chat_id: str, streamed: AsyncMock
) -> None:
    """The registry marks the exit before the host hears of it, so the agent can read the result first."""
    release = asyncio.Event()
    append_message = ChatService.append_message

    async def held(*args: object, **kwargs: object) -> object:
        await release.wait()
        return await append_message(*args, **kwargs)

    with patch.object(ChatService, "append_message", held):
        pid = await agent.start_job("print('built')")
        await _until(_exited(pid), "the job to exit")

        waited = await agent.process(action="wait", pid=pid, timeout_seconds=10)

        assert waited["content"]["stdout"] == ["built"]
        assert chat_id not in wake_turn_scheduler._waiting, "the host has not heard of the finish yet"
        release.set()
        await _until(_wake_queued(chat_id), "the finish to queue a wake turn")

    await _end_the_agents_turn(chat_id)
    streamed.assert_not_awaited()
