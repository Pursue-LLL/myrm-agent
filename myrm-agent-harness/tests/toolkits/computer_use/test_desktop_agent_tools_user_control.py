"""Desktop tools behind the person's control: a held control stops them, a stale screen never gets clicked."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.computer_use.desktop_agent_tools import create_desktop_tools
from myrm_agent_harness.utils.runtime import cancellation
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, set_cancel_token
from myrm_agent_harness.utils.runtime.user_control import UserControl

_NOTICE_HEAD = "Not run: a person used the desktop"
_STOPPED_NOTICE = "Not run: the run was stopped while a person was driving the desktop."


@pytest.fixture
def _fast_poll(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(cancellation, "_POLL_INTERVAL_S", 0.02)
    monkeypatch.setattr(cancellation, "_ABORT_GRACE_S", 0.2)
    yield
    set_cancel_token(None)


def _tools() -> tuple[dict[str, BaseTool], MagicMock]:
    session = MagicMock()
    session.user_control = UserControl()
    session.observed_generation = session.user_control.generation
    session.desktop_snapshot = AsyncMock(return_value="tree")
    session.desktop_interact = AsyncMock(return_value="clicked")
    session.desktop_vision_capture = AsyncMock(return_value="screen")
    session.desktop_vision_action = AsyncMock(return_value="moved")
    session._backend.is_browser_active = AsyncMock(return_value=False)
    return {tool.name: tool for tool in create_desktop_tools(session)}, session


def _hand_over(session: MagicMock) -> None:
    session.user_control.acquire()
    session.user_control.release()


@pytest.mark.asyncio
async def test_every_desktop_tool_waits_while_a_person_drives() -> None:
    tools, session = _tools()
    session.user_control.acquire()

    pending = [
        asyncio.create_task(tools["desktop_snapshot_tool"].ainvoke({})),
        asyncio.create_task(tools["desktop_interact_tool"].ainvoke({"ref": "d1", "action": "click"})),
        asyncio.create_task(tools["desktop_vision_tool"].ainvoke({"action": "screenshot"})),
    ]
    await asyncio.sleep(0.05)

    assert not any(task.done() for task in pending)
    session.desktop_snapshot.assert_not_called()
    session.desktop_interact.assert_not_called()
    session.desktop_vision_capture.assert_not_called()
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_an_action_after_a_hand_over_needs_a_fresh_snapshot() -> None:
    tools, session = _tools()
    _hand_over(session)

    refused = await tools["desktop_interact_tool"].ainvoke({"ref": "d1", "action": "click"})
    assert str(refused).startswith(_NOTICE_HEAD)
    session.desktop_interact.assert_not_called()

    await tools["desktop_snapshot_tool"].ainvoke({})
    assert await tools["desktop_interact_tool"].ainvoke({"ref": "d1", "action": "click"}) == "clicked"


@pytest.mark.asyncio
async def test_a_vision_capture_looks_and_a_vision_click_acts() -> None:
    tools, session = _tools()
    _hand_over(session)

    refused = await tools["desktop_vision_tool"].ainvoke({"action": "left_click", "coordinate": [5, 5]})
    assert str(refused).startswith(_NOTICE_HEAD)
    session.desktop_vision_action.assert_not_called()

    assert await tools["desktop_vision_tool"].ainvoke({"action": "capture"}) == "screen"
    assert await tools["desktop_vision_tool"].ainvoke({"action": "left_click", "coordinate": [5, 5]}) == "moved"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_fast_poll")
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("desktop_snapshot_tool", {}),
        ("desktop_interact_tool", {"ref": "d1", "action": "click"}),
        ("desktop_vision_tool", {"action": "screenshot"}),
        ("desktop_vision_tool", {"action": "left_click", "coordinate": [5, 5]}),
    ],
)
async def test_stopping_the_run_ends_every_desktop_tool_that_waits_for_the_person(
    tool_name: str, arguments: dict[str, object]
) -> None:
    tools, session = _tools()
    session.user_control.acquire()
    token = CancellationToken("req")
    set_cancel_token(token)
    asyncio.get_running_loop().call_later(0.05, token.cancel)

    began = time.monotonic()
    result = await asyncio.wait_for(tools[tool_name].ainvoke(arguments), timeout=3.0)

    assert result == _STOPPED_NOTICE
    assert time.monotonic() - began < 3.0
    assert session.user_control.held is True
    for action in (session.desktop_snapshot, session.desktop_interact, session.desktop_vision_capture):
        action.assert_not_called()
    session.desktop_vision_action.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_fast_poll")
async def test_a_desktop_tool_still_runs_after_a_stopped_run_when_the_person_hands_back() -> None:
    tools, session = _tools()
    session.user_control.acquire()
    token = CancellationToken("req")
    token.cancel()
    set_cancel_token(token)
    assert await asyncio.wait_for(tools["desktop_snapshot_tool"].ainvoke({}), timeout=3.0) == _STOPPED_NOTICE

    set_cancel_token(CancellationToken("next"))
    session.user_control.release()

    assert await tools["desktop_snapshot_tool"].ainvoke({}) == "tree"
