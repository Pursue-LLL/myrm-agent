"""Real-loop tests for the workspace context a chat thread is shown: the sandbox snapshot is taken once per thread and stays byte-identical, the rules stay live.

[INPUT]
- agent.workspace_rules.middleware::WorkspaceRulesMiddleware (POS: workspace context injection middleware under test)
- langchain.agents::create_agent + a scripted model (POS: the real agent loop; the middleware is never called by hand)
- runtime.checkpointing.factory::create_checkpointer (POS: the checkpointer the product runs with, a SQLite file in a temp dir)

[OUTPUT]
- Fails when a model call regenerates the snapshot, when the text of the workspace context changes because the agent edited the workspace, when a workspace switch or a new thread is
  served a stale snapshot, when the rules stop being read live, or when a workspace the trust gate blocks is probed or injected.

[POS]
The injection is a per-request override and never lands in the graph state, so only a run through the real loop shows what the model is sent on each call. Every scripted turn edits
the workspace between its two model calls, which is what a coding session does.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from myrm_agent_harness.agent.security.workspace_trust.context import set_workspace_trust_level
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel
from myrm_agent_harness.agent.workspace_rules.middleware import WorkspaceRulesMiddleware
from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer
from myrm_agent_harness.toolkits.code_execution import sandbox_snapshot

_SNAPSHOT_BLOCK = re.compile(r"<sandbox_environment_snapshot>.*?</sandbox_environment_snapshot>", re.DOTALL)


def _snapshot_block(workspace_context: str) -> str:
    match = _SNAPSHOT_BLOCK.search(workspace_context)
    assert match is not None, "the workspace context carries no sandbox snapshot"
    return match.group(0)


class _ScriptedModel(BaseChatModel):
    """Calls the tool at the start of every turn, answers once the tool has replied, and records the workspace context each request carried."""

    workspace_contexts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        carried = [str(m.content) for m in messages if "<workspace_context" in str(m.content)]
        self.workspace_contexts.append("\n".join(carried))
        if isinstance(messages[-1], ToolMessage):
            reply = AIMessage(content="done")
        else:
            reply = AIMessage(
                content="", tool_calls=[{"name": "add_file", "args": {}, "id": f"call-{len(self.workspace_contexts)}"}]
            )
        return ChatResult(generations=[ChatGeneration(message=reply)])


class _Session:
    """One agent with the middleware under test; every ``turn`` is one ``ainvoke`` on a chat thread."""

    def __init__(self, checkpointer: BaseCheckpointSaver[str]) -> None:
        self.model = _ScriptedModel()
        self._edited_root: Path | None = None

        @tool
        def add_file() -> str:
            """Create one more file in the workspace."""
            assert self._edited_root is not None
            (self._edited_root / f"added_{len(list(self._edited_root.iterdir()))}.txt").write_text("x")
            return "ok"

        self.agent = create_agent(
            self.model,
            tools=[add_file],
            middleware=[WorkspaceRulesMiddleware()],
            checkpointer=checkpointer,
            system_prompt="system",
        )

    async def turn(self, root: Path, thread_id: str = "chat-1") -> list[str]:
        """Run one turn in ``root``; return the workspace context of each model call the turn made."""
        self._edited_root = root
        already_seen = len(self.model.workspace_contexts)
        await self.agent.ainvoke(
            {"messages": [HumanMessage(content="go")]},
            {"configurable": {"thread_id": thread_id}},
            # The product passes a plain dict as the run context and declares no schema for it.
            context={"workspace_path": str(root)},  # type: ignore[call-overload]
        )
        return self.model.workspace_contexts[already_seen:]


@contextmanager
def _trust(level: WorkspaceTrustLevel) -> Iterator[None]:
    set_workspace_trust_level(level)
    try:
        yield
    finally:
        set_workspace_trust_level(None)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# Project rules\nUse type hints.\n")
    (root / "README.md").write_text("project\n")
    return root


@pytest.fixture
def session() -> _Session:
    return _Session(MemorySaver())


@pytest.fixture
def generated() -> Iterator[list[str]]:
    """The roots the snapshot was generated for, in order."""
    roots: list[str] = []
    real = sandbox_snapshot.generate_sandbox_bootstrap_snapshot

    def recording(workspace_path: str | Path, max_entries: int = 25) -> sandbox_snapshot.SandboxBootstrapSnapshot:
        roots.append(str(workspace_path))
        return real(workspace_path, max_entries=max_entries)

    with patch.object(sandbox_snapshot, "generate_sandbox_bootstrap_snapshot", recording):
        yield roots


class TestSnapshotIsTakenOncePerThread:
    async def test_the_agent_editing_the_workspace_does_not_change_what_the_model_is_sent(
        self, session: _Session, workspace: Path, generated: list[str]
    ) -> None:
        with _trust(WorkspaceTrustLevel.TRUSTED):
            sent = [context for _ in range(3) for context in await session.turn(workspace)]

        assert len(sent) == 6, "three turns of two model calls each"
        assert len(set(sent)) == 1, "the text must not move while the agent adds files"
        assert generated == [str(workspace)], "one generation for the whole thread"
        assert "added_" not in sent[0], "the snapshot describes the workspace as the conversation began"

    async def test_another_thread_gets_a_snapshot_of_its_own(
        self, session: _Session, workspace: Path, generated: list[str]
    ) -> None:
        with _trust(WorkspaceTrustLevel.TRUSTED):
            await session.turn(workspace, thread_id="chat-a")
            second = await session.turn(workspace, thread_id="chat-b")

        assert len(generated) == 2
        assert "added_" in second[0], "the new thread starts from the workspace as it is now"

    async def test_a_changed_workspace_takes_a_fresh_snapshot(
        self, session: _Session, workspace: Path, tmp_path: Path, generated: list[str]
    ) -> None:
        other = tmp_path / "other"
        other.mkdir()
        (other / "AGENTS.md").write_text("# Other rules\n")

        with _trust(WorkspaceTrustLevel.TRUSTED):
            first = await session.turn(workspace)
            second = await session.turn(other)

        assert generated == [str(workspace), str(other)]
        assert f"Working Directory: {workspace}" in first[0]
        assert f"Working Directory: {other}" in second[0]
        assert f"Working Directory: {workspace}" not in second[0]

    async def test_the_product_checkpointer_keeps_the_snapshot_between_turns(
        self, workspace: Path, tmp_path: Path, generated: list[str]
    ) -> None:
        checkpointer, cleanup = await create_checkpointer(
            mode="sqlite", sqlite_db_path=str(tmp_path / "checkpoints.db")
        )
        try:
            session = _Session(checkpointer)
            with _trust(WorkspaceTrustLevel.TRUSTED):
                sent = [context for _ in range(2) for context in await session.turn(workspace)]
        finally:
            await cleanup()

        assert len(set(sent)) == 1
        assert generated == [str(workspace)]


class TestRulesStayLive:
    async def test_an_edited_rule_file_reaches_the_next_call_while_the_snapshot_stays_frozen(
        self, session: _Session, workspace: Path
    ) -> None:
        with _trust(WorkspaceTrustLevel.TRUSTED):
            first = (await session.turn(workspace))[0]
            (workspace / "AGENTS.md").write_text("# Project rules\nPrefer small functions.\n")
            second = (await session.turn(workspace))[0]

        assert "Use type hints." in first
        assert "Prefer small functions." in second
        assert "Use type hints." not in second
        assert _snapshot_block(first) == _snapshot_block(second)


class TestTrustGate:
    @pytest.mark.parametrize("level", [WorkspaceTrustLevel.RESTRICTED, WorkspaceTrustLevel.REVOKED])
    async def test_a_blocked_workspace_is_neither_probed_nor_injected(
        self, session: _Session, workspace: Path, generated: list[str], level: WorkspaceTrustLevel
    ) -> None:
        with _trust(level):
            sent = await session.turn(workspace)

        assert generated == [], "no git or file probe may run in a workspace the gate blocks"
        assert sent == ["", ""]

    async def test_a_workspace_trusted_mid_thread_is_probed_from_then_on(
        self, session: _Session, workspace: Path, generated: list[str]
    ) -> None:
        with _trust(WorkspaceTrustLevel.RESTRICTED):
            before = await session.turn(workspace)
        with _trust(WorkspaceTrustLevel.TRUSTED):
            after = await session.turn(workspace)

        assert before == ["", ""]
        assert generated == [str(workspace)]
        assert all("<sandbox_environment_snapshot>" in context for context in after)


class TestAPassingRunIsNotVacuous:
    async def test_the_scripted_turn_really_edits_the_workspace(self, session: _Session, workspace: Path) -> None:
        with _trust(WorkspaceTrustLevel.TRUSTED):
            await session.turn(workspace)

        assert (workspace / "added_2.txt").exists()
