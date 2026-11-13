"""A kanban run that stops on a request only a person can answer blocks its task for the user instead of failing and retrying.

[INPUT]
- app.services.kanban.task_runner::KanbanTaskRunner (POS: the production run entry; the agent stream is the only stand-in)
- app.services.kanban.task_runner.stream::_StreamAccumulator (POS: reads the stop and its reason off the stream events)
- app.services.kanban.task_runner.outcomes::resolve_run_outcome, APPROVAL_NEEDED_BLOCK_REASON, TAKEOVER_NEEDED_BLOCK_REASON (POS: the verdict on a finished run)
- myrm_agent_harness KanbanDispatcher + InMemoryKanbanStore (POS: the scheduler that retried such a run before it was blocked)
- myrm_agent_harness interrupt_events + build_interrupt_payload + ToolStuckException (POS: build the pause events exactly as a paused run emits them)

[OUTPUT]
Pins the path of one task: its stream ends on an approval or on a browser step that needs a person (a login, a captcha),
which nobody can give while a task runs; the run blocks the task for the user with that request's fixed reason, and the
dispatcher neither retries it nor counts a failure. A loop guard pause and a stream error stay failures; a task that blocked
itself or completed keeps that verdict.

[POS]
tests/services/kanban/test_task_runner_approval_stop.py
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolCall
from langgraph.types import Interrupt
from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.agent.middlewares.approval.batch_processor import build_interrupt_payload
from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks
from myrm_agent_harness.agent.streaming.interrupt_events import interrupt_events
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    KANBAN_COMPLETION_INTENT_KEY,
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskEventKind,
    TaskExecutionResult,
    TaskRunOutcome,
    TaskStatus,
)

from app.core.types import ModelConfig
from app.services.kanban.task_runner import KanbanTaskRunner
from app.services.kanban.task_runner.outcomes import (
    APPROVAL_NEEDED_BLOCK_REASON,
    PROTOCOL_VIOLATION_MSG,
    TAKEOVER_NEEDED_BLOCK_REASON,
    resolve_run_outcome,
)
from app.services.kanban.task_runner.stream import _StreamAccumulator

_RUNNER = "app.services.kanban.task_runner.runner"
BOARD_ID = "b1"
TASK_ID = "task0001"
WAIT_SECONDS = 20


def _paused_on(interrupt_value: Mapping[str, object]) -> dict[str, object]:
    """The stream event the harness emits when the graph pauses on this interrupt value."""
    return interrupt_events([Interrupt(value=interrupt_value, id="interrupt-1")], "message-1")[0]


_SHELL_CALL: ToolCall = {"name": "shell_exec", "args": {"command": "rm -rf build"}, "id": "call-1", "type": "tool_call"}
TOOL_APPROVAL = _paused_on(
    build_interrupt_payload([(0, _SHELL_CALL, "shell_exec", "requires approval", None)], f"kanban:{TASK_ID}")[0]
)
OTHER_APPROVAL = _paused_on(
    {"action_type": "high_risk_dom_action", "tool_name": "browser_click", "reason": "Submits a payment form"}
)
# What `browser_ask_human` raises when the agent meets a login or a captcha.
BROWSER_TAKEOVER = _paused_on(
    {"action_type": "browser_takeover", "tool_name": "browser_ask_human_tool", "reason": "Log in to continue"}
)
LOOP_GUARD_PAUSE = _paused_on(ToolStuckException("The same call failed 5 times").interrupt_payload("shell_exec", "call-1"))
STOPS = [(TOOL_APPROVAL, APPROVAL_NEEDED_BLOCK_REASON), (BROWSER_TAKEOVER, TAKEOVER_NEEDED_BLOCK_REASON)]  # pause, reason
RUN_ERROR: dict[str, object] = {"type": "error", "error": "provider down", "error_type": "LLMError"}
EMPTY_ANSWER = (False, "agent returned empty response")


def _task(
    *,
    status: TaskStatus = TaskStatus.READY,
    goal_mode: bool = False,
    metadata: dict[str, object] | None = None,
    result: str = "",
    blocked_reason: str | None = None,
    block_kind: BlockKind | None = None,
) -> KanbanTask:
    return KanbanTask(
        task_id=TASK_ID,
        board_id=BOARD_ID,
        title="Weekly digest",
        status=status,
        goal_mode=goal_mode,
        metadata=metadata or {},
        result=result,
        blocked_reason=blocked_reason,
        block_kind=block_kind,
    )


def _fed(*events: dict[str, object]) -> _StreamAccumulator:
    acc = _StreamAccumulator()
    for event in events:
        acc.add(event)
    return acc


class TestAccumulator:
    @pytest.mark.parametrize(
        ("event", "reason"),
        [
            (TOOL_APPROVAL, APPROVAL_NEEDED_BLOCK_REASON),
            (OTHER_APPROVAL, APPROVAL_NEEDED_BLOCK_REASON),
            ({"type": "approval_required"}, APPROVAL_NEEDED_BLOCK_REASON),
            (BROWSER_TAKEOVER, TAKEOVER_NEEDED_BLOCK_REASON),
        ],
    )
    def test_a_request_only_a_person_can_answer_ends_the_stream_with_its_reason(
        self, event: dict[str, object], reason: str
    ) -> None:
        assert _fed({"type": "message", "data": "starting"}, event).unanswered_request_reason == reason

    @pytest.mark.parametrize(
        ("events", "reason"),
        [
            ((TOOL_APPROVAL, BROWSER_TAKEOVER), APPROVAL_NEEDED_BLOCK_REASON),
            ((BROWSER_TAKEOVER, TOOL_APPROVAL), TAKEOVER_NEEDED_BLOCK_REASON),
        ],
    )
    def test_the_first_request_names_the_reason(self, events: tuple[dict[str, object], ...], reason: str) -> None:
        assert _fed(*events).unanswered_request_reason == reason

    def test_a_stream_without_one_did_not_stop_on_a_request(self) -> None:
        assert _fed({"type": "message", "data": "hi"}, {"type": "message_end"}).unanswered_request_reason is None

    def test_the_loop_guard_pause_is_no_request(self) -> None:
        assert LOOP_GUARD_PAUSE["type"] == "approval_required"  # typed like an approval; only its action type tells
        assert _fed(LOOP_GUARD_PAUSE).unanswered_request_reason is None

    @pytest.mark.parametrize("events", [(TOOL_APPROVAL, RUN_ERROR), (RUN_ERROR, TOOL_APPROVAL), (BROWSER_TAKEOVER, RUN_ERROR)])
    def test_a_run_error_outranks_the_request(self, events: tuple[dict[str, object], ...]) -> None:
        assert _fed(*events).unanswered_request_reason is None


async def _verdict(
    task: KanbanTask, agent_result: tuple[bool, str], request_reason: str | None
) -> tuple[bool, str] | TaskExecutionResult:
    """What the end of a run means for ``task`` when its stream ended on the request with this reason (None: on none)."""
    store = AsyncMock()
    store.get_task.return_value = task
    return await resolve_run_outcome(store, TASK_ID, agent_result, request_reason=request_reason)


class TestVerdict:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_result", [(True, "I will run the build next"), EMPTY_ANSWER])
    @pytest.mark.parametrize("reason", [APPROVAL_NEEDED_BLOCK_REASON, TAKEOVER_NEEDED_BLOCK_REASON])
    async def test_a_stop_on_a_request_blocks_the_task_for_the_user_with_its_reason(
        self, agent_result: tuple[bool, str], reason: str
    ) -> None:
        outcome = await _verdict(_task(), agent_result, reason)

        assert isinstance(outcome, TaskExecutionResult)
        assert outcome.is_blocked
        assert outcome.blocked_reason == reason
        assert outcome.block_kind == BlockKind.HUMAN

    @pytest.mark.asyncio
    async def test_without_the_stop_a_run_that_did_not_complete_is_still_a_protocol_violation(self) -> None:
        outcome = await _verdict(_task(), (True, "forgot kanban_complete"), None)

        assert outcome == (False, PROTOCOL_VIOLATION_MSG)

    @pytest.mark.asyncio
    async def test_a_task_that_blocked_itself_keeps_its_own_reason(self) -> None:
        task = _task(status=TaskStatus.BLOCKED, blocked_reason="Need the API key", block_kind=BlockKind.EXTERNAL)

        outcome = await _verdict(task, (True, "x"), APPROVAL_NEEDED_BLOCK_REASON)

        assert isinstance(outcome, TaskExecutionResult)
        assert (outcome.blocked_reason, outcome.block_kind) == ("Need the API key", BlockKind.EXTERNAL)

    @pytest.mark.asyncio
    async def test_a_task_that_completed_stays_completed(self) -> None:
        task = _task(metadata={KANBAN_COMPLETION_INTENT_KEY: True}, result="Finished the digest")

        outcome = await _verdict(task, (True, "stream text"), APPROVAL_NEEDED_BLOCK_REASON)

        assert outcome == (True, "Finished the digest")

    @pytest.mark.asyncio
    async def test_a_verdict_already_reached_is_passed_on(self) -> None:
        reached = TaskExecutionResult.failure("goal budget spent")

        outcome = await resolve_run_outcome(AsyncMock(), TASK_ID, reached, request_reason=TAKEOVER_NEEDED_BLOCK_REASON)

        assert outcome is reached


def _agent_streaming(events: list[dict[str, object]], result: tuple[bool, str]) -> AsyncMock:
    """What the agent run does to the caller's accumulator: feed it the stream's events, then report its text."""

    async def execute(*_args: object, acc: _StreamAccumulator, **_kwargs: object) -> tuple[bool, str]:
        for event in events:
            acc.add(event)
        return result

    return AsyncMock(side_effect=execute)


@contextmanager
def _run_surfaces(runner: KanbanTaskRunner, execute_agent: AsyncMock | None = None) -> Iterator[None]:
    """The run entry with its inputs fixed; ``execute_agent`` stands in for the whole agent run when given."""
    with ExitStack() as stack:
        stack.enter_context(patch(f"{_RUNNER}.build_task_context", new=AsyncMock(return_value="context")))
        stack.enter_context(patch(f"{_RUNNER}.resolve_agent_profile", new=AsyncMock(return_value=None)))
        stack.enter_context(patch(f"{_RUNNER}.resolve_workspace", new=AsyncMock(return_value=None)))
        stack.enter_context(patch(f"{_RUNNER}.build_multimodal_query", new=AsyncMock(return_value="query")))
        if execute_agent is not None:
            stack.enter_context(patch.object(runner, "_execute_agent", execute_agent))
        yield


@contextmanager
def _real_agent_run(runner: KanbanTaskRunner, stream: Callable[..., AsyncIterator[dict[str, object]]]) -> Iterator[None]:
    """The real agent run: only what it reads (configuration, model, the agent and its event stream) is replaced."""
    model_cfg = ModelConfig(model="test-model", api_key="test-key")
    configs = MagicMock()
    configs.retrieval_dict = {}
    configs.providers_dict = {"providers": []}
    configs.security_config_dict = {}
    configs.search_cfg = {"searchService": "tavily"}
    configs.search_is_user_configured = False
    settings = MagicMock()
    settings.database.event_log_dir = "/tmp/kanban-approval-stop-test"
    settings.event_log_max_jsonl_line_bytes = 1024
    with ExitStack() as stack:
        stack.enter_context(_run_surfaces(runner))
        stack.enter_context(patch("app.ai_agents.agents.AgentFactory.create_general_agent", return_value=AsyncMock()))
        stack.enter_context(patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=configs)))
        stack.enter_context(patch("app.core.channel_bridge.model_resolver.resolve_model_config", return_value=model_cfg))
        stack.enter_context(patch("app.core.channel_bridge.model_resolver.enrich_model_capabilities", return_value=model_cfg))
        stack.enter_context(patch("app.core.channel_bridge.model_resolver.enrich_model_context_window", return_value=model_cfg))
        stack.enter_context(patch("app.services.agent.swarm_fission_resume.stream_with_swarm_fission_resume", new=stream))
        stack.enter_context(patch("app.config.settings.get_settings", return_value=settings))
        yield


async def _seeded_store(task: KanbanTask) -> InMemoryKanbanStore:
    store = InMemoryKanbanStore()
    await store.save_board(
        KanbanBoard(
            board_id=BOARD_ID,
            name="Board",
            settings=BoardSettings(max_concurrent_tasks=2, heartbeat_interval_seconds=1, zombie_timeout_seconds=60),
        )
    )
    await store.save_task(task)
    return store


class TestRun:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_result", [(True, "I will run the build next"), EMPTY_ANSWER])
    @pytest.mark.parametrize(("pause", "reason"), STOPS)
    async def test_a_run_that_stops_on_a_request_blocks_its_task_with_its_reason(
        self, agent_result: tuple[bool, str], pause: dict[str, object], reason: str
    ) -> None:
        runner = KanbanTaskRunner(await _seeded_store(_task()))

        with _run_surfaces(runner, _agent_streaming([pause], agent_result)):
            outcome = await runner.run(_task())

        assert isinstance(outcome, TaskExecutionResult)
        assert (outcome.is_blocked, outcome.blocked_reason, outcome.block_kind) == (True, reason, BlockKind.HUMAN)

    @pytest.mark.asyncio
    async def test_a_goal_mode_run_blocks_the_same_way(self) -> None:
        runner = KanbanTaskRunner(await _seeded_store(_task(goal_mode=True)))

        with (
            _run_surfaces(runner, _agent_streaming([TOOL_APPROVAL], (True, "partial"))),
            patch.object(runner, "_setup_goal_provider", new=AsyncMock(return_value=MagicMock())),
            patch.object(runner, "_map_goal_outcome", new=AsyncMock(side_effect=lambda _t, _p, result: result)),
        ):
            outcome = await runner.run(_task(goal_mode=True))

        assert isinstance(outcome, TaskExecutionResult)
        assert outcome.blocked_reason == APPROVAL_NEEDED_BLOCK_REASON

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("events", "result"),
        [
            pytest.param([LOOP_GUARD_PAUSE], EMPTY_ANSWER, id="loop-guard-pause"),
            pytest.param([TOOL_APPROVAL, RUN_ERROR], (False, "LLMError: provider down"), id="stream-error"),
        ],
    )
    async def test_a_failure_stays_a_failure(self, events: list[dict[str, object]], result: tuple[bool, str]) -> None:
        runner = KanbanTaskRunner(await _seeded_store(_task()))

        with _run_surfaces(runner, _agent_streaming(events, result)):
            outcome = await runner.run(_task())

        assert outcome == result

    @pytest.mark.asyncio
    async def test_every_run_reads_its_own_stream(self) -> None:
        runner = KanbanTaskRunner(await _seeded_store(_task()))

        with _run_surfaces(runner, _agent_streaming([TOOL_APPROVAL], (True, "partial"))):
            first = await runner.run(_task())
        with _run_surfaces(runner, _agent_streaming([], (True, "done without kanban_complete"))):
            second = await runner.run(_task())

        assert isinstance(first, TaskExecutionResult)
        assert first.is_blocked
        assert second == (False, PROTOCOL_VIOLATION_MSG)


class TestRealAgentRun:
    """Through the real agent run, so the accumulator the runner reads is the one the run's events were fed to."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("pause", "reason"), STOPS)
    async def test_a_request_in_the_agent_stream_blocks_the_task_with_its_reason(
        self, pause: dict[str, object], reason: str
    ) -> None:
        async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "I will run the build next"}
            yield pause

        runner = KanbanTaskRunner(await _seeded_store(_task()))

        with _real_agent_run(runner, stream):
            outcome = await runner.run(_task())

        assert isinstance(outcome, TaskExecutionResult)
        assert outcome.blocked_reason == reason

    @pytest.mark.asyncio
    async def test_a_stream_that_ends_without_completing_still_fails(self) -> None:
        async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "I will run the build next"}
            yield {"type": "message_end"}

        runner = KanbanTaskRunner(await _seeded_store(_task()))

        with _real_agent_run(runner, stream):
            outcome = await runner.run(_task())

        assert outcome == (False, PROTOCOL_VIOLATION_MSG)


async def _until(store: InMemoryKanbanStore, done: Callable[[KanbanTask], bool]) -> KanbanTask:
    async def poll() -> KanbanTask:
        while (task := await store.get_task(TASK_ID)) is None or not done(task):
            await asyncio.sleep(0.02)
        return task

    return await asyncio.wait_for(poll(), timeout=WAIT_SECONDS)


@pytest.mark.asyncio
async def test_the_dispatcher_holds_the_task_for_the_user_without_retrying_it() -> None:
    store = await _seeded_store(_task())
    runner = KanbanTaskRunner(store)
    execute_agent = _agent_streaming([TOOL_APPROVAL], (True, "I will run the build next"))
    board = await store.get_board(BOARD_ID)
    assert board is not None
    dispatcher = KanbanDispatcher(store, runner, board)

    with _run_surfaces(runner, execute_agent):
        await dispatcher.start()
        try:
            await _until(store, lambda task: task.status in (TaskStatus.BLOCKED, TaskStatus.FAILED))
            # A retry would have queued the task again and run the agent a second time within this pause.
            await asyncio.sleep(0.3)
            held = await store.get_task(TASK_ID)
        finally:
            await dispatcher.stop()
            await wait_all_background_tasks(timeout_seconds=WAIT_SECONDS)

    assert held is not None
    assert held.status == TaskStatus.BLOCKED
    assert (held.block_kind, held.blocked_reason) == (BlockKind.HUMAN, APPROVAL_NEEDED_BLOCK_REASON)
    assert (held.retry_count, held.consecutive_failures) == (0, 0)
    assert execute_agent.await_count == 1
    assert [run.outcome for run in await store.list_runs(TASK_ID)] == [TaskRunOutcome.BLOCKED]
    assert not [
        event for event in await store.list_events(TASK_ID) if event.kind in (TaskEventKind.RETRYING, TaskEventKind.FAILED)
    ]
