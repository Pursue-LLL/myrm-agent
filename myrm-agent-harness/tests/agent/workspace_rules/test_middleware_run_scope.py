"""Real-loop tests for the workspace context a chat thread is shown: the sandbox snapshot is taken once per
thread, off the event loop, without an extra checkpoint, and stays byte-identical, the rules stay live.

[INPUT]
- agent.workspace_rules.middleware::WorkspaceRulesMiddleware (POS: workspace context injection middleware under test)
- langchain.agents::create_agent + a scripted model (POS: the real agent loop; the middleware is never called by hand)
- runtime.checkpointing.factory::create_checkpointer (POS: the checkpointer the product runs with, a SQLite file in a temp dir)

[OUTPUT]
- Fails when a model call regenerates the snapshot, when the text of the workspace context changes because
  the agent edited the workspace, when a workspace switch or a new thread is served a stale snapshot, when
  the rules stop being read live, when a workspace the trust gate blocks is probed or injected, when taking
  the snapshot stalls the event loop or adds checkpoints to the thread, or when an interrupted and resumed
  run is sent another snapshot than it started with.

[POS]
The injection is a per-request override and never lands in the graph state, so only a run through the real
loop shows what the model is sent on each call. Every scripted turn edits the workspace between its two
model calls, which is what a coding session does.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from pydantic import Field

from myrm_agent_harness.agent.security.workspace_trust.context import set_workspace_trust_level
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel
from myrm_agent_harness.agent.workspace_rules import middleware
from myrm_agent_harness.agent.workspace_rules.middleware import WorkspaceRulesMiddleware
from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer
from myrm_agent_harness.toolkits.code_execution import sandbox_snapshot

_SNAPSHOT_BLOCK = re.compile(r"<sandbox_environment_snapshot>.*?</sandbox_environment_snapshot>", re.DOTALL)


def _snapshot_block(workspace_context: str) -> str:
    match = _SNAPSHOT_BLOCK.search(workspace_context)
    assert match is not None, "the workspace context carries no sandbox snapshot"
    return match.group(0)


class _ScriptedModel(BaseChatModel):
    """Calls ``tool_name`` at the start of every turn, answers once the tool has replied, and records the
    workspace context each request carried; its first ``failing_calls`` calls fail."""

    workspace_contexts: list[str] = Field(default_factory=list)
    tool_name: str = "add_file"
    failing_calls: int = 0

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
        if len(self.workspace_contexts) <= self.failing_calls:
            raise RuntimeError("provider unavailable")
        if isinstance(messages[-1], ToolMessage):
            reply = AIMessage(content="done")
        else:
            reply = AIMessage(
                content="",
                tool_calls=[{"name": self.tool_name, "args": {}, "id": f"call-{len(self.workspace_contexts)}"}],
            )
        return ChatResult(generations=[ChatGeneration(message=reply)])


class _Session:
    """One agent, with the middleware under test unless ``with_middleware`` is off; every ``turn`` is one run
    on a chat thread."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver[str],
        *,
        model: _ScriptedModel | None = None,
        with_middleware: bool = True,
    ) -> None:
        self.model = model or _ScriptedModel()
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
            middleware=[WorkspaceRulesMiddleware()] if with_middleware else [],
            checkpointer=checkpointer,
            system_prompt="system",
        )

    async def turn(self, root: Path, thread_id: str = "chat-1", *, streaming: bool = False) -> list[str]:
        """Run one turn in ``root``, streamed as the product does or not; return the workspace context of each
        model call the turn made."""
        self._edited_root = root
        already_seen = len(self.model.workspace_contexts)
        # The product passes a plain dict as the run context and declares no schema for it.
        if streaming:
            async for _chunk in self.agent.astream(
                {"messages": [HumanMessage(content="go")]},
                {"configurable": {"thread_id": thread_id}},
                context={"workspace_path": str(root)},  # type: ignore[call-overload]
                stream_mode=["messages", "updates"],
            ):
                pass
        else:
            await self.agent.ainvoke(
                {"messages": [HumanMessage(content="go")]},
                {"configurable": {"thread_id": thread_id}},
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

    async def test_the_streamed_run_the_product_uses_takes_and_keeps_it_too(
        self, session: _Session, workspace: Path, generated: list[str]
    ) -> None:
        with _trust(WorkspaceTrustLevel.TRUSTED):
            sent = [context for _ in range(2) for context in await session.turn(workspace, streaming=True)]

        assert len(sent) == 4
        assert len(set(sent)) == 1
        assert "<sandbox_environment_snapshot>" in sent[0]
        assert generated == [str(workspace)]


class TestTakingTheSnapshotCostsTheRunNothingElse:
    async def test_a_slow_probe_does_not_stall_the_event_loop(self, session: _Session, workspace: Path) -> None:
        probe_seconds = 0.6
        real = sandbox_snapshot.generate_sandbox_bootstrap_snapshot

        def slow(workspace_path: str | Path, max_entries: int = 25) -> sandbox_snapshot.SandboxBootstrapSnapshot:
            time.sleep(probe_seconds)
            return real(workspace_path, max_entries=max_entries)

        gaps: list[float] = []
        running = True

        async def heartbeat() -> None:
            last = time.perf_counter()
            while running:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now

        with (
            patch.object(sandbox_snapshot, "generate_sandbox_bootstrap_snapshot", slow),
            _trust(WorkspaceTrustLevel.TRUSTED),
        ):
            beat = asyncio.create_task(heartbeat())
            started = time.perf_counter()
            await session.turn(workspace)
            elapsed = time.perf_counter() - started
            running = False
            await beat

        assert elapsed >= probe_seconds, "the slow probe really ran inside the turn"
        assert max(gaps) < probe_seconds / 2, (
            f"another task was kept waiting {max(gaps):.2f} s while the snapshot was taken"
        )

    async def test_the_thread_is_checkpointed_as_often_as_without_the_middleware(self, workspace: Path) -> None:
        async def checkpoints_after_two_turns(*, with_middleware: bool) -> int:
            session = _Session(MemorySaver(), with_middleware=with_middleware)
            with _trust(WorkspaceTrustLevel.TRUSTED):
                for _ in range(2):
                    await session.turn(workspace)
            config: RunnableConfig = {"configurable": {"thread_id": "chat-1"}}
            return len([state async for state in session.agent.aget_state_history(config)])

        baseline = await checkpoints_after_two_turns(with_middleware=False)
        with_it = await checkpoints_after_two_turns(with_middleware=True)

        assert baseline > 0
        assert with_it == baseline, (
            "keeping the snapshot in the thread must not add a graph step, and with it a checkpoint, to each model call"
        )


class TestInterruptedAndFailedRuns:
    async def test_a_resumed_run_is_sent_the_snapshot_it_started_with(
        self, workspace: Path, tmp_path: Path, generated: list[str]
    ) -> None:
        @tool
        def ask_the_user() -> str:
            """Ask the user to approve."""
            return str(interrupt("approve?"))

        checkpointer, cleanup = await create_checkpointer(
            mode="sqlite", sqlite_db_path=str(tmp_path / "checkpoints.db")
        )
        model = _ScriptedModel(tool_name="ask_the_user")
        try:
            agent = create_agent(
                model,
                tools=[ask_the_user],
                middleware=[WorkspaceRulesMiddleware()],
                checkpointer=checkpointer,
                system_prompt="system",
            )
            config: RunnableConfig = {"configurable": {"thread_id": "chat-1"}}
            context = {"workspace_path": str(workspace)}
            with _trust(WorkspaceTrustLevel.TRUSTED):
                await agent.ainvoke({"messages": [HumanMessage(content="go")]}, config, context=context)  # type: ignore[call-overload]
                (workspace / "added_while_waiting.txt").write_text("x")
                await agent.ainvoke(Command(resume="approved"), config, context=context)  # type: ignore[call-overload]
        finally:
            await cleanup()

        assert len(model.workspace_contexts) == 2, "one call before the interrupt, one after the resume"
        assert len(set(model.workspace_contexts)) == 1
        assert "<sandbox_environment_snapshot>" in model.workspace_contexts[0]
        assert generated == [str(workspace)]

    async def test_a_failed_first_call_leaves_nothing_behind_and_the_retry_is_served_a_snapshot(
        self, workspace: Path, generated: list[str]
    ) -> None:
        session = _Session(MemorySaver(), model=_ScriptedModel(failing_calls=1))
        with _trust(WorkspaceTrustLevel.TRUSTED):
            with pytest.raises(RuntimeError, match="provider unavailable"):
                await session.turn(workspace)
            generated_before_retry = len(generated)
            retried = await session.turn(workspace)

        assert len(retried) == 2
        assert all("<sandbox_environment_snapshot>" in context for context in retried)
        assert len(set(retried)) == 1
        assert len(generated) - generated_before_retry <= 1, (
            "the retry takes the snapshot at most once; its second call reads it back"
        )

    async def test_a_stopped_run_returns_at_once_while_the_snapshot_is_taken_and_leaves_nothing_behind(
        self, workspace: Path
    ) -> None:
        probing = threading.Event()
        real = sandbox_snapshot.generate_sandbox_bootstrap_snapshot

        def slow(workspace_path: str | Path, max_entries: int = 25) -> sandbox_snapshot.SandboxBootstrapSnapshot:
            probing.set()
            time.sleep(1.0)
            return real(workspace_path, max_entries=max_entries)

        session = _Session(MemorySaver())
        with (
            patch.object(sandbox_snapshot, "generate_sandbox_bootstrap_snapshot", slow),
            _trust(WorkspaceTrustLevel.TRUSTED),
        ):
            run = asyncio.create_task(session.turn(workspace))
            while not probing.is_set():
                await asyncio.sleep(0.01)
            stopped_at = time.perf_counter()
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run
            returned_in = time.perf_counter() - stopped_at

        assert returned_in < 0.5, f"the stopped run was held for {returned_in:.2f} s by the probe"
        assert session.model.workspace_contexts == [], "the stopped run never reached the model"
        config: RunnableConfig = {"configurable": {"thread_id": "chat-1"}}
        assert "workspace_snapshot" not in (await session.agent.aget_state(config)).values


class TestAProbeThatNeverReturns:
    async def test_the_thread_goes_on_without_a_snapshot_and_is_never_made_to_wait_again(self, workspace: Path) -> None:
        release = threading.Event()
        started: list[str] = []
        real = sandbox_snapshot.generate_sandbox_bootstrap_snapshot

        def hung(workspace_path: str | Path, max_entries: int = 25) -> sandbox_snapshot.SandboxBootstrapSnapshot:
            started.append(str(workspace_path))
            release.wait(5.0)
            return real(workspace_path, max_entries=max_entries)

        saver = MemorySaver()
        session = _Session(saver)
        with (
            patch.object(sandbox_snapshot, "generate_sandbox_bootstrap_snapshot", hung),
            patch.object(middleware, "_SNAPSHOT_DEADLINE_MS", 300.0),
            _trust(WorkspaceTrustLevel.TRUSTED),
        ):
            try:
                started_at = time.perf_counter()
                first = await session.turn(workspace)
                first_turn_seconds = time.perf_counter() - started_at
                second = await session.turn(workspace)
            finally:
                release.set()

        assert first_turn_seconds < 3.0, f"the first turn waited {first_turn_seconds:.1f} s for the probe"
        assert len(started) == 1, "the probe is abandoned for the thread, not retried by the later calls"
        for context in (*first, *second):
            assert "Use type hints." in context, "the rules are still sent"
            assert "<sandbox_environment_snapshot>" not in context
        config: RunnableConfig = {"configurable": {"thread_id": "chat-1"}}
        held = saver.get_tuple(config)
        assert held is not None
        assert held.checkpoint["channel_values"]["workspace_snapshot"] == ""


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
