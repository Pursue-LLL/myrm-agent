"""browser_execute_script_tool: what a call does around the script (attribution, hand-over pin, results, verification)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.snapshot.aria_types import RefInfo
from myrm_agent_harness.toolkits.browser.tools import execute_script
from myrm_agent_harness.toolkits.browser.tools.execute_script import create_execute_script_tool
from myrm_agent_harness.utils.runtime.user_control import UserControl, in_plan, plan_is_stale


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session._hitl_caller_tool = None
    session.observed_generation = 3
    session.get_all_refs.return_value = {}
    session.notify_progress = AsyncMock()
    session.list_downloads.return_value = []
    session.interact = AsyncMock(return_value="clicked")
    session.evaluate = AsyncMock(return_value="42")
    return session


@pytest.mark.asyncio
async def test_hitl_caller_is_the_script_tool_while_it_runs_and_cleared_after(mock_session: MagicMock) -> None:
    seen: list[str | None] = []

    async def interact(action: str, ref: str, text: str = "") -> str:
        seen.append(mock_session._hitl_caller_tool)
        return "clicked"

    mock_session.interact = interact
    tool = create_execute_script_tool(mock_session)

    await tool.ainvoke({"script": "await session.interact('click', 'e1')"})

    assert seen == ["browser_execute_script_tool"]
    assert mock_session._hitl_caller_tool is None


@pytest.mark.asyncio
async def test_hitl_caller_cleared_after_timeout(mock_session: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    async def never_finishes(action: str, ref: str, text: str = "") -> str:
        await asyncio.sleep(30)
        return "unreachable"

    mock_session.interact = never_finishes
    monkeypatch.setattr(execute_script, "_SCRIPT_TIMEOUT_S", 0.3)
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "await session.interact('click', 'e1')"})

    assert "timed out" in result.lower()
    assert mock_session._hitl_caller_tool is None


@pytest.mark.asyncio
async def test_hitl_caller_cleared_after_runtime_error(mock_session: MagicMock) -> None:
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "raise RuntimeError('boom')"})

    assert "Runtime exception" in result
    assert "boom" in result
    assert mock_session._hitl_caller_tool is None


@pytest.mark.asyncio
async def test_a_rejected_script_never_touches_the_session(mock_session: MagicMock) -> None:
    tool = create_execute_script_tool(mock_session)

    syntax = await tool.ainvoke({"script": "def foo(:"})
    imports = await tool.ainvoke({"script": "import os"})

    assert "SyntaxError" in syntax
    assert "Imports are unavailable" in imports
    mock_session.notify_progress.assert_not_awaited()
    mock_session.interact.assert_not_awaited()
    assert mock_session._hitl_caller_tool is None


@pytest.mark.asyncio
async def test_the_steps_a_script_takes_reach_the_session(mock_session: MagicMock) -> None:
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke(
        {"script": "print(await session.interact('type', 'e2', 'hello'))\nprint(await session.evaluate('1 + 41'))"}
    )

    mock_session.interact.assert_awaited_once_with("type", "e2", "hello")
    mock_session.evaluate.assert_awaited_once_with("1 + 41")
    assert "clicked" in result
    assert "42" in result


@pytest.mark.asyncio
async def test_refs_reach_the_script_as_role_name_and_nth(mock_session: MagicMock) -> None:
    mock_session.get_all_refs.return_value = {"e1": RefInfo(role="button", name="Save", nth=2)}
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "print(refs['e1'])"})

    assert "'role': 'button'" in result
    assert "'name': 'Save'" in result
    assert "'nth': 2" in result


@pytest.mark.asyncio
async def test_every_step_is_pinned_to_the_hand_over_the_model_last_observed(mock_session: MagicMock) -> None:
    pinned: list[tuple[bool, bool, bool]] = []

    async def interact(action: str, ref: str, text: str = "") -> str:
        same = cast("UserControl", SimpleNamespace(generation=mock_session.observed_generation))
        later = cast("UserControl", SimpleNamespace(generation=mock_session.observed_generation + 1))
        pinned.append((in_plan(), plan_is_stale(same), plan_is_stale(later)))
        return "clicked"

    mock_session.interact = interact
    tool = create_execute_script_tool(mock_session)

    await tool.ainvoke({"script": "await session.interact('click', 'e1')"})

    assert pinned == [(True, False, True)]
    assert in_plan() is False, "the pin ends with the call"


@pytest.mark.asyncio
async def test_successful_print_output_is_marked_untrusted(mock_session: MagicMock) -> None:
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "print('hello from script')"})

    assert "hello from script" in result
    assert "Source: browser" in result, "what a page can influence is handed to the model as untrusted"


@pytest.mark.asyncio
async def test_no_output_returns_success_message(mock_session: MagicMock) -> None:
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "x = 1"})

    assert "Script executed successfully" in result


@pytest.mark.asyncio
async def test_progress_brackets_the_run(mock_session: MagicMock) -> None:
    tool = create_execute_script_tool(mock_session)

    await tool.ainvoke({"script": "print('before')\nawait session.interact('click', 'e1')"})

    messages = [call.args[0] for call in mock_session.notify_progress.await_args_list]
    assert messages == [
        "Starting browser script execution...",
        "[Script] before",
        "Browser script execution completed.",
    ]


@pytest.mark.asyncio
async def test_verify_goal_with_mock_page(mock_session: MagicMock) -> None:
    mock_page = MagicMock()
    mock_page.locator.return_value = MagicMock()
    mock_page.screenshot = AsyncMock(return_value=b"fake_png")
    mock_session._tab_controller.get_active_page.return_value = mock_page
    mock_session._vision_verifier = MagicMock()
    mock_session._vision_verifier.verify_action = AsyncMock(return_value=(True, "[PASS] Goal met"))
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "print('done')", "verify_goal": "Page loaded"})

    assert "[PASS] Goal met" in result


@pytest.mark.asyncio
async def test_verify_goal_screenshot_failure_graceful(mock_session: MagicMock) -> None:
    mock_session._tab_controller.get_active_page.side_effect = Exception("No page")
    tool = create_execute_script_tool(mock_session)

    result = await tool.ainvoke({"script": "print('ok')", "verify_goal": "Something"})

    assert "ok" in result
