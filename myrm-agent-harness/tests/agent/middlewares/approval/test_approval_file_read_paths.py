"""The shipped approval stack judges the files ``file_read_tool`` receives in ``paths``.

The model reads files through a ``paths`` list, never through the ``path`` the engine used to look at, so a
read of a credential file or of anything outside the workspace ran without a verdict and without a card. These
tests send real ``file_read_tool`` calls through the middleware stack and check what the user is asked, what is
refused outright and what runs.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import set_security_config, set_workspace_root
from myrm_agent_harness.agent.middlewares.approval import set_approval_session
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.session_access import set_session_access_roots
from myrm_agent_harness.agent.security.types import AccessRoot, PathPolicy, PrivacyPolicy, SecurityConfig

files_read: list[list[str]] = []


@tool
def file_read_tool(paths: list[str], mode: str = "all") -> str:
    """Record which files were read."""
    files_read.append(paths)
    return "contents"


class ScriptedModel(BaseChatModel):
    """Calls the read tool with the scripted arguments, then answers."""

    reads: list[list[str]]
    mode: str = "all"
    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        if self.served < len(self.reads):
            call = {
                "id": f"c{self.served}",
                "name": "file_read_tool",
                "args": {"paths": self.reads[self.served], "mode": self.mode},
            }
            reply = AIMessage(content="", tool_calls=[call])
        else:
            reply = AIMessage(content="done")
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


class Layout:
    """A workspace, a forbidden directory and a directory outside every zone."""

    def __init__(self, root: Path) -> None:
        self.workspace = root / "ws"
        self.forbidden = root / "secrets"
        self.downloads = root / "downloads"
        for directory in (self.workspace, self.forbidden, self.downloads):
            directory.mkdir()


@pytest.fixture
def layout(tmp_path: Path) -> Iterator[Layout]:
    root = tmp_path.resolve()
    where = Layout(root)
    files_read.clear()
    clear_all_session_denials_for_tests()
    set_session_access_roots(())
    set_security_config(
        SecurityConfig(
            yolo_mode_enabled=False,
            privacy_policy=PrivacyPolicy(enabled=False),
            path_policy=PathPolicy(forbidden_paths=frozenset({str(where.forbidden)}), access_roots=()),
        )
    )
    set_workspace_root(str(where.workspace))
    set_approval_session("file-read-paths")
    yield where
    set_security_config(None)
    set_workspace_root("")
    set_approval_session("")
    set_session_access_roots(())
    clear_all_session_denials_for_tests()


def _agent(*reads: list[str], mode: str = "all") -> CompiledStateGraph:
    return create_agent(
        ScriptedModel(reads=list(reads), mode=mode),
        tools=[file_read_tool],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


_CONFIG = {"configurable": {"thread_id": "t"}}


async def _run(agent: CompiledStateGraph) -> dict[str, object]:
    return await agent.ainvoke({"messages": [HumanMessage(content="read it")]}, _CONFIG)


@pytest.mark.parametrize("mode", ["all", "preview", "stream"])
async def test_a_read_in_the_forbidden_zone_is_refused_outright(layout: Layout, mode: str) -> None:
    result = await _run(_agent([str(layout.forbidden / "id_rsa")], mode=mode))

    assert "__interrupt__" not in result
    assert files_read == []
    answers = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.status for m in answers] == ["error"]


async def test_one_forbidden_file_in_a_batch_refuses_the_whole_call(layout: Layout) -> None:
    (layout.workspace / "a.py").write_text("x")

    result = await _run(_agent(["a.py", str(layout.forbidden / "id_rsa")]))

    assert files_read == []
    assert [m.status for m in result["messages"] if isinstance(m, ToolMessage)] == ["error"]


async def test_a_read_outside_the_zones_waits_for_the_user_and_runs_once_approved(layout: Layout) -> None:
    target = str(layout.downloads / "bill.csv")
    agent = _agent([target], mode="preview")

    paused = await _run(agent)
    assert paused["__interrupt__"]
    assert files_read == []

    await agent.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), _CONFIG)
    assert files_read == [[target]]


async def test_a_read_the_user_refuses_never_runs(layout: Layout) -> None:
    agent = _agent([str(layout.downloads / "bill.csv")], mode="preview")

    assert (await _run(agent))["__interrupt__"]
    result = await agent.ainvoke(Command(resume={"decisions": [{"type": "reject", "feedback": "no"}]}), _CONFIG)

    assert files_read == []
    assert [m.status for m in result["messages"] if isinstance(m, ToolMessage)] == ["error"]


async def test_a_directory_the_user_granted_earlier_lets_its_files_through_without_a_card(layout: Layout) -> None:
    granted = str(layout.downloads / "a.csv"), str(layout.downloads / "sub" / "b.csv")
    set_session_access_roots((AccessRoot(path=str(layout.downloads), writable=False, source="path_ask_grant"),))

    result = await _run(_agent(list(granted), mode="preview"))

    assert "__interrupt__" not in result
    assert files_read == [list(granted)]


async def test_a_granted_directory_does_not_open_the_forbidden_zone(layout: Layout) -> None:
    set_session_access_roots((AccessRoot(path=str(layout.downloads), writable=False, source="path_ask_grant"),))

    result = await _run(_agent([str(layout.downloads / "a.csv"), str(layout.forbidden / "id_rsa")]))

    assert files_read == []
    assert [m.status for m in result["messages"] if isinstance(m, ToolMessage)] == ["error"]


async def test_a_secret_file_inside_the_workspace_waits_for_the_user(layout: Layout) -> None:
    result = await _run(_agent(["a.py", "config/.env"]))

    assert result["__interrupt__"]
    assert files_read == []


@pytest.mark.parametrize("path", ["src/a.py", "/mcp/gmail/send_email.md", "vault://0a1b2c:1-50"])
async def test_reads_the_tool_serves_inside_the_workspace_or_its_own_namespaces_run_without_a_card(
    layout: Layout, path: str
) -> None:
    result = await _run(_agent([path]))

    assert "__interrupt__" not in result
    assert files_read == [[path]]
