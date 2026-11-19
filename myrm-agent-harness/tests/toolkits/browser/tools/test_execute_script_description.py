"""browser_execute_script_tool tells the model the script contract that the runtime enforces."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from myrm_agent_harness.toolkits.browser.tools import create_browser_tools
from myrm_agent_harness.toolkits.browser.tools.execute_script import _SCRIPT_TIMEOUT_S, create_execute_script_tool


@pytest.fixture
def session() -> MagicMock:
    stub = MagicMock()
    stub.get_all_refs.return_value = {"e1": SimpleNamespace(role="button", name="OK", nth=0)}
    stub.notify_progress = AsyncMock()
    stub.interact = AsyncMock()
    return stub


def test_wire_description_states_the_script_contract(session: MagicMock) -> None:
    description = convert_to_openai_tool(create_execute_script_tool(session))["function"]["description"]

    for fact in ("session.interact", "refs", "print()", "browser_interact_tool", f"{_SCRIPT_TIMEOUT_S:.0f} s"):
        assert fact in description


@pytest.mark.asyncio
async def test_runtime_honours_the_stated_contract(session: MagicMock) -> None:
    tool = create_execute_script_tool(session)
    script = "await session.interact('click', 'e1')\nprint(refs['e1']['role'], refs['e1']['name'])"

    result = await tool.ainvoke({"script": script})

    session.interact.assert_awaited_once_with("click", "e1")
    assert "button OK" in result
    assert "ImportError" in await tool.ainvoke({"script": "import os"})
    assert "NameError" in await tool.ainvoke({"script": "open('x')"})


def test_no_browser_tool_keeps_text_in_its_schema_class_docstring(session: MagicMock) -> None:
    """LangChain sends the tool description or function docstring, never the args_schema class docstring."""
    assert [tool.name for tool in create_browser_tools(session) if tool.args_schema.__doc__] == []
