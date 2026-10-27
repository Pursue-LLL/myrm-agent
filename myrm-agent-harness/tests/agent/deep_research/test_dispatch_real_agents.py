"""Three real research agents fetch the same page at once; none of them may count another's calls as its own.

Researchers on one topic often fetch the same URL. Sharing one loop guard, their identical calls added up
to a single loop and the guard broke agents that had each fetched only a few times. Each agent has its own
budget: it is allowed `_BREAK_AT - 1` fetches of the page and broken on the next, whatever the others do.

A researcher is also given the turns it is configured with: every turn is a model round that may call tools,
however many middlewares the agent's graph has and however many tools it calls at once. It spends all of them
and then reports what it found.

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
_ENDLESS = 1000


class _FetchSamePageModel(BaseChatModel):
    """Asks for pages again after every result, until it has asked `fetches` times.

    With `same_page` it asks for one URL every time; otherwise each request is a page of its own.
    Each round asks for `calls_per_round` pages at once.
    """

    fetches: int = _FETCHES_PER_AGENT
    same_page: bool = True
    calls_per_round: int = 1

    @property
    def _llm_type(self) -> str:
        return "fetch-same-page"

    def bind_tools(self, tools: object, **kwargs: object) -> _FetchSamePageModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        asked = sum(isinstance(message, ToolMessage) for message in messages)
        if asked < self.fetches:
            calls = [
                {
                    "name": "web_fetch_tool",
                    "args": {"url": "https://shared.test/page" if self.same_page else f"https://shared.test/page/{n}"},
                    "id": f"call_{n}",
                }
                for n in range(asked, asked + self.calls_per_round)
            ]
            reply = AIMessage(content="", tool_calls=calls)
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
        config=DeepResearchConfig(),
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


@pytest.mark.parametrize(("turns", "calls_per_round"), [(16, 1), (8, 3)])
@pytest.mark.asyncio
async def test_a_research_agent_spends_the_turns_it_is_configured_with_and_reports(
    tmp_path: Path, turns: int, calls_per_round: int
) -> None:
    """Every turn is a round of tool calls, not graph bookkeeping; the run ends on its turn limit, not before."""
    fetched_under: Counter[int] = Counter()
    orchestrator = DeepResearchOrchestrator(
        llm=_FetchSamePageModel(fetches=_ENDLESS, same_page=False, calls_per_round=calls_per_round),
        config=DeepResearchConfig(max_research_agent_turns=turns),
        parent_tools=[_fetch_tool(fetched_under)],
        context={"session_id": "chat_parent", "workspaces_storage_root": str(tmp_path)},
    )
    orchestrator._start_time = 1.0

    findings = await orchestrator._dispatch_research_agents(
        tasks=[{"task": "look into a", "tc_id": "tc_a"}], message_id="msg"
    )

    assert sum(fetched_under.values()) == turns * calls_per_round
    assert findings and findings[0] != "[No findings]"
