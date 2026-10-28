"""Through the shipped approval stack and the real file tool, an approved call reaches the file it named.

The approval node and the tool node run in separate copies of the context, and the executor refuses a path outside
the workspace that nothing granted. These tests send real ``file_read_tool`` calls through the middleware stack and
check what the executor then does, so the hand-off between the nodes is what is under test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.middlewares._session_context import set_security_config, set_workspace_root
from myrm_agent_harness.agent.middlewares.approval import set_approval_session
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.session_access import set_session_access_roots
from myrm_agent_harness.agent.security.types import PathPolicy, PrivacyPolicy, SecurityConfig
from myrm_agent_harness.core.context_vars import access_grants_var, open_access_grants, scoped_value, workspace_root_var
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor


class ReadsThenAnswers(BaseChatModel):
    """Reads one file per model turn, then answers."""

    reads: list[str]
    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ReadsThenAnswers:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        if self.served < len(self.reads):
            call = {"id": f"c{self.served}", "name": "file_read_tool", "args": {"paths": [self.reads[self.served]]}}
            reply = AIMessage(content="", tool_calls=[call])
        else:
            reply = AIMessage(content="done")
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture
def places(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    root = tmp_path.resolve()
    workspace, outside = root / "ws", root / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "a.txt").write_text("alpha from outside")
    (outside / "b.txt").write_text("beta from outside")
    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(workspace))
    set_executor(executor)
    workspace_root_var.set(str(workspace))
    clear_all_session_denials_for_tests()
    set_security_config(
        SecurityConfig(
            yolo_mode_enabled=False,
            privacy_policy=PrivacyPolicy(enabled=False),
            path_policy=PathPolicy(forbidden_paths=frozenset(), access_roots=()),
        )
    )
    set_workspace_root(str(workspace))
    set_approval_session("once-grants-graph")
    with scoped_value(access_grants_var, None):
        set_session_access_roots(())
        yield workspace, outside
        set_session_access_roots(())
    set_security_config(None)
    set_workspace_root("")
    set_approval_session("")
    clear_all_session_denials_for_tests()


def _agent(*reads: str) -> CompiledStateGraph:
    return create_agent(
        ReadsThenAnswers(reads=list(reads)),
        tools=[create_file_read_tool(skills=[])],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


_CONFIG = {"configurable": {"thread_id": "t"}}


async def _start(agent: CompiledStateGraph) -> dict[str, object]:
    open_access_grants(())
    return await agent.ainvoke({"messages": [HumanMessage(content="read it")]}, _CONFIG)


async def _answer(agent: CompiledStateGraph, extensions: dict[str, object]) -> dict[str, object]:
    open_access_grants(())
    return await agent.ainvoke(Command(resume={"decisions": [{"type": "approve", "extensions": extensions}]}), _CONFIG)


def _tool_answers(result: dict[str, object]) -> list[str]:
    messages = result["messages"]
    assert isinstance(messages, list)
    return [str(m.content) for m in messages if isinstance(m, ToolMessage)]


async def test_an_approved_read_returns_the_file_it_named(places: tuple[Path, Path]) -> None:
    _, outside = places
    agent = _agent(str(outside / "a.txt"))

    assert (await _start(agent))["__interrupt__"]
    answers = _tool_answers(await _answer(agent, {}))

    assert len(answers) == 1
    assert "alpha from outside" in answers[0]


async def test_the_approval_does_not_open_the_next_read_of_the_same_file(places: tuple[Path, Path]) -> None:
    _, outside = places
    agent = _agent(str(outside / "a.txt"), str(outside / "a.txt"))

    assert (await _start(agent))["__interrupt__"]
    second = await _answer(agent, {})

    assert second["__interrupt__"], "a plain approval covers one call; the next read asks again"


async def test_the_approval_does_not_open_a_sibling_file(places: tuple[Path, Path]) -> None:
    _, outside = places
    agent = _agent(str(outside / "a.txt"), str(outside / "b.txt"))

    assert (await _start(agent))["__interrupt__"]
    second = await _answer(agent, {})

    assert second["__interrupt__"], "the sibling is a different file: it asks as well"


async def test_remembering_the_folder_lets_its_next_read_through_without_a_card(places: tuple[Path, Path]) -> None:
    _, outside = places
    agent = _agent(str(outside / "a.txt"), str(outside / "b.txt"))

    assert (await _start(agent))["__interrupt__"]
    result = await _answer(agent, {"grantDirectory": True})

    assert "__interrupt__" not in result
    answers = _tool_answers(result)
    assert "alpha from outside" in answers[0]
    assert "beta from outside" in answers[1]
