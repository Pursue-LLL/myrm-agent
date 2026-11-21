"""browser_execute_script_tool tells the model the script contract that the runtime enforces."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from myrm_agent_harness.toolkits.browser.session import BrowserSession
from myrm_agent_harness.toolkits.browser.snapshot.aria_types import RefInfo
from myrm_agent_harness.toolkits.browser.tools import create_browser_tools, script_runtime
from myrm_agent_harness.toolkits.browser.tools.execute_script import _SCRIPT_TIMEOUT_S, create_execute_script_tool


@pytest.fixture
def session() -> MagicMock:
    stub = MagicMock()
    stub.get_all_refs.return_value = {"e1": RefInfo(role="button", name="OK", nth=0)}
    stub.notify_progress = AsyncMock()
    stub.interact = AsyncMock(return_value="done")
    return stub


def test_wire_description_states_the_script_contract(session: MagicMock) -> None:
    description = convert_to_openai_tool(create_execute_script_tool(session))["function"]["description"]

    for fact in ("session.interact", "refs", "print()", "browser_interact_tool", f"{_SCRIPT_TIMEOUT_S:.0f} s"):
        assert fact in description


@pytest.mark.asyncio
async def test_runtime_honours_the_stated_contract(session: MagicMock, tmp_path: Path) -> None:
    tool = create_execute_script_tool(session)
    script = "await session.interact('click', 'e1')\nprint(refs['e1']['role'], refs['e1']['name'])"

    result = await tool.ainvoke({"script": script})

    session.interact.assert_awaited_once_with("click", "e1", "")
    assert "button OK" in result
    assert "Imports are unavailable" in await tool.ainvoke({"script": "import os"})
    written = tmp_path / "written-by-the-script"
    assert "[Error]" in await tool.ainvoke({"script": f"open({str(written)!r}, 'w').write('x')"})
    assert not written.exists()


def test_the_steps_a_script_can_take_exist_on_the_real_session_with_the_arguments_the_runtime_passes() -> None:
    """A renamed parameter would not show in the mock-based tests; the real class does."""
    for name in script_runtime._STEP_NAMES:
        assert inspect.iscoroutinefunction(getattr(BrowserSession, name)), name
    assert list(inspect.signature(BrowserSession.interact).parameters)[1:4] == ["action", "ref", "text"]
    assert list(inspect.signature(BrowserSession.evaluate).parameters)[1:] == ["expression"]


def test_no_browser_tool_keeps_text_in_its_schema_class_docstring(session: MagicMock) -> None:
    """LangChain sends the tool description or function docstring, never the args_schema class docstring."""
    assert [tool.name for tool in create_browser_tools(session) if tool.args_schema.__doc__] == []
