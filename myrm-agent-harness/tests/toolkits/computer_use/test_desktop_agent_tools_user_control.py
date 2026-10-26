"""Desktop tools behind the person's control: a held control stops them, a stale screen never gets clicked."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.computer_use.desktop_agent_tools import create_desktop_tools
from myrm_agent_harness.utils.runtime.user_control import UserControl

_NOTICE_HEAD = "Not run: a person used the desktop"


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
