"""A call to a tool the run does not have is answered with the skills hint only when the run has ``skill_select_tool``.

The hint tells the model to load a skill with ``skill_select_tool``. To a run without that tool, such as one whose host
switched the built-in tools off, it would name a tool the model cannot call.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from myrm_agent_harness.agent.middlewares._session_context import set_active_resolved_tools
from tests.support.shipped_graph import shipped_agent, shipped_session

_SKILLS_HINT = (
    "Hint: Do not confuse tools with skills. Tools are for LLM to call directly. "
    "Skills (ending with _skill) are operation manuals for certain workflows and cannot be called directly by LLM. "
    "You must first use skill_select_tool to select a skill, then learn from its documentation!"
)


@tool
def host_tool(query: str) -> str:
    """Answer from the host's own data."""
    return "answer"


@tool("skill_select_tool")
def skill_select_tool(skill_names: str) -> str:
    """Load a skill."""
    return "skill"


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with shipped_session(tmp_path):
        yield


async def _answer_to_a_call_of_an_unknown_tool(bound: list[BaseTool]) -> str:
    """The error a run bound with *bound* sends the model back after it called a tool nobody has."""
    set_active_resolved_tools(bound)
    call = AIMessage(content="", tool_calls=[{"id": "c1", "name": "imaginary_skill", "args": {}}])
    _, agent = shipped_agent([call, AIMessage(content="done")], [host_tool])

    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    (answer,) = (message for message in result["messages"] if isinstance(message, ToolMessage))
    assert answer.status == "error"
    return str(answer.content)


@pytest.mark.asyncio
async def test_a_run_with_skill_select_tool_is_told_to_load_skills_with_it() -> None:
    answer = await _answer_to_a_call_of_an_unknown_tool([host_tool, skill_select_tool])

    assert answer == f"Error: 'imaginary_skill' is not a valid tool. Please retry.\n\n{_SKILLS_HINT}"


@pytest.mark.asyncio
async def test_a_run_without_skill_select_tool_is_not_sent_to_it() -> None:
    answer = await _answer_to_a_call_of_an_unknown_tool([host_tool])

    assert answer == "Error: 'imaginary_skill' is not a valid tool. Please retry."
