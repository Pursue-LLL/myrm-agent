"""Three real research agents fetch the same page at once; none of them may count another's calls as its own.

Researchers on one topic often fetch the same URL. Sharing one loop guard, their identical calls added up
to a single loop and the guard broke agents that had each fetched only a few times. Each agent has its own
budget: it is allowed `_BREAK_AT - 1` fetches of the page and broken on the next, whatever the others do.

The dispatch, the agents' runs, the tool interceptor and its loop guard are real; only the model is scripted.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, StructuredTool

from myrm_agent_harness.agent.deep_research.config import DeepResearchConfig
from myrm_agent_harness.agent.deep_research.orchestrator import DeepResearchOrchestrator
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import get_loop_guard
from tests.agent.sub_agents.guard_state_probe import guard_state

pytestmark = pytest.mark.usefixtures("parent_run")

_FETCHES_PER_AGENT = 14
_BREAK_AT = 10  # identical calls a LoopGuard allows before it breaks the loop


class _FetchSamePageModel(BaseChatModel):
    """Asks for the same page again after every result, until it has asked `_FETCHES_PER_AGENT` times."""

    @property
    def _llm_type(self) -> str:
        return "fetch-same-page"

    def bind_tools(self, tools: object, **kwargs: object) -> _FetchSamePageModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        asked = sum(isinstance(message, ToolMessage) for message in messages)
        if asked < _FETCHES_PER_AGENT:
            call = {"name": "web_fetch_tool", "args": {"url": "https://shared.test/page"}, "id": f"call_{asked}"}
            reply = AIMessage(content="", tool_calls=[call])
        else:
            reply = AIMessage(content="findings")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _fetch_tool(fetched_under: Counter[int]) -> BaseTool:
    async def fetch(url: str) -> str:
        fetched_under[id(get_loop_guard())] += 1
        return f"page at {url}"

    return StructuredTool.from_function(coroutine=fetch, name="web_fetch_tool", description="Fetch a page.")


@pytest.mark.asyncio
async def test_research_agents_fetching_the_same_page_each_get_their_own_loop_budget(tmp_path: Path) -> None:
    parent_guard, parent = get_loop_guard(), guard_state()
    fetched_under: Counter[int] = Counter()
    orchestrator = DeepResearchOrchestrator(
        llm=_FetchSamePageModel(),
        config=DeepResearchConfig(max_research_agent_turns=100),
        parent_tools=[_fetch_tool(fetched_under)],
        context={"session_id": "chat_parent", "workspaces_storage_root": str(tmp_path)},
    )
    orchestrator._start_time = 1.0

    await orchestrator._dispatch_research_agents(
        tasks=[{"task": f"look into {topic}", "tc_id": f"tc_{topic}"} for topic in ("a", "b", "c")],
        message_id="msg_research",
    )

    assert id(parent_guard) not in fetched_under
    assert sorted(fetched_under.values()) == [_BREAK_AT - 1] * 3
    assert guard_state() == parent
