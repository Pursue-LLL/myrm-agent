"""A steer or redirect a run has accepted reaches the model, on a fresh turn and on a turn resumed after an approval.

The first half drives the real ``create_agent`` loop, the real steering middleware and a real checkpointer through
``StreamExecutor.execute()``: a steer lands while a tool is running, the middleware cancels the remaining tool calls,
and the message must then be read by the model. It also covers the two ways an accepted message could still be lost:
the pass restarted by error recovery, and the moment between the last steering check and the end of the turn. The
second half pins what the steering handler leaves as the next input for each kind of turn.
"""

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import tool_interceptor_middleware
from myrm_agent_harness.agent.streaming.stream_executor import StreamExecutor
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.core.message_origin import is_user_authored_human_message
from myrm_agent_harness.toolkits.llms.errors.exceptions import MyrmLLMError
from myrm_agent_harness.utils.runtime.steering import SteeringToken, set_steering_token

from .scripted_agent import THREAD_ID, TRACKER_PATH, ScriptedModel, Turn, make_context, make_executor

REQUEST = "do the job"
STEER = "USER: use the 2024 data instead"
LATE_STEER = "USER: and cite the source"
TIMEOUT_S = 10
JITTER_PATH = "myrm_agent_harness.toolkits.llms.reliability.jittered_backoff.calculate_adaptive_jittered_delay"


def tool_turn(name: str, args: dict[str, object], call_id: str) -> Turn:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}]), "tool_calls"


def answer(text: str) -> Turn:
    return AIMessage(content=text), "stop"


async def _allow_hooks(*_args: object, **_kwargs: object) -> SimpleNamespace:
    """What the tool interceptor reads from the hook layer: nothing blocks and nothing rewrites the call."""
    return SimpleNamespace(blocked=False, reason="", updated_input=None, all_succeeded=True)


@pytest.fixture
def tracker():
    tracker = MagicMock(last_finish_reason=None, usage=None, total_cost_usd=0.0)
    with (
        patch("myrm_agent_harness.agent.hooks.executor.fire_hook", new=_allow_hooks),
        patch(TRACKER_PATH, return_value=tracker),
    ):
        yield tracker
    set_steering_token(None)


class FlakyModel(ScriptedModel):
    """Raises ``error`` once on request number ``fail_on`` (0: never), before that request is recorded or scripted."""

    fail_on: int = 0
    error: str = "timeout"
    failed: bool = False

    async def _agenerate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        if not self.failed and len(self.requests) + 1 == self.fail_on:
            self.failed = True
            raise Exception(self.error)
        return self._respond(messages)


class Scenario:
    """The agent loop under test: a ``work`` tool the test holds open and a ``gate`` tool that asks for approval."""

    def __init__(self, tracker: MagicMock, turns: list[Turn], fail_on: int = 0, error: str = "timeout") -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.executed: list[int] = []

        @tool("work")
        async def work(step: int) -> str:
            """Do one step of work."""
            self.executed.append(step)
            self.started.set()
            await self.release.wait()
            return f"step {step} done"

        @tool("gate")
        async def gate(path: str) -> str:
            """Ask for approval before writing."""
            return f"approved:{interrupt({'path': path})}"

        self.model = FlakyModel(turns=turns, tracker=tracker, fail_on=fail_on, error=error)
        self.agent = create_agent(
            model=self.model,
            tools=[work, gate],
            middleware=[tool_interceptor_middleware],
            checkpointer=InMemorySaver(),
        )

    async def run(
        self,
        agent_input: object,
        token: SteeringToken,
        during_work: Callable[[], object] | None = None,
    ) -> StreamExecutor:
        """Run one pass; ``during_work`` fires while the first ``work`` step is open, then that step finishes."""
        set_steering_token(token)  # the product binds the run's token the same way
        context = make_context(self.agent, agent_input, thread_id=THREAD_ID)
        context.steering_token = token
        executor = make_executor(context)
        run = asyncio.create_task(executor.execute())
        if during_work is not None:
            await asyncio.wait_for(self.started.wait(), TIMEOUT_S)
            during_work()
            self.release.set()
        await asyncio.wait_for(run, TIMEOUT_S)
        return executor

    async def paused_on_approval(self) -> bool:
        return bool((await self.agent.aget_state({"configurable": {"thread_id": THREAD_ID}})).interrupts)

    async def thread(self) -> list[BaseMessage]:
        return (await self.agent.aget_state({"configurable": {"thread_id": THREAD_ID}})).values["messages"]

    def read_by_model(self, text: str) -> bool:
        return any(("HumanMessage", text) == message for request in self.model.requests for message in request.messages)


def events_of(executor: StreamExecutor, event_type: AgentEventType) -> list[dict[str, object]]:
    return [
        event
        for event in executor._compactor.events
        if isinstance(event, dict) and event.get("type") == event_type.value
    ]


# ---------------------------------------------------------------------------
# Real agent loop: a steer that lands while a tool is running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("resumed", [False, True], ids=["fresh", "resumed"])
async def test_a_steer_landing_during_a_tool_is_read_by_the_model(tracker: MagicMock, resumed: bool):
    """The run cancels the calls the steer overtook and then hands the steer to the model, whichever kind of turn."""
    turns = [
        tool_turn("work", {"step": 1}, "w1"),
        tool_turn("work", {"step": 2}, "w2"),  # overtaken by the steer: cancelled, never run
        answer("stopping here"),
        answer("following the new instruction"),
    ]
    if resumed:
        turns.insert(0, tool_turn("gate", {"path": "report.md"}, "g1"))
    scenario = Scenario(tracker, turns)
    first_input = {"messages": [HumanMessage(content=REQUEST)]}
    token = SteeringToken()

    if resumed:
        await scenario.run(first_input, SteeringToken())
        assert await scenario.paused_on_approval()
        executor = await scenario.run(Command(resume="approved"), token, lambda: token.steer(STEER))
    else:
        executor = await scenario.run(first_input, token, lambda: token.steer(STEER))

    assert events_of(executor, AgentEventType.ERROR) == []
    assert scenario.executed == [1]
    assert len(scenario.model.requests) == len(turns)  # every scripted generation was requested, none missing
    assert scenario.read_by_model(STEER)
    assert [event["data"]["count"] for event in events_of(executor, AgentEventType.STEERING)] == [1]
    assert token.has_pending is False

    thread = await scenario.thread()
    contents = [str(message.content) for message in thread]
    assert contents.count(REQUEST) == 1
    assert contents.count(STEER) == 1
    ids = [message.id for message in thread]
    assert len(ids) == len(set(ids)), "the continued turn must not duplicate messages already in its thread"


@pytest.mark.asyncio
async def test_a_steer_survives_the_pass_that_error_recovery_restarts(tracker: MagicMock):
    """The finished tool already took the steer off the queue; the pass then fails and runs again, still owing it."""
    turns = [
        tool_turn("work", {"step": 1}, "w1"),
        answer("stopping here"),  # the model's second request fails once before this
        answer("following the new instruction"),
    ]
    scenario = Scenario(tracker, turns, fail_on=2)
    token = SteeringToken()

    with patch(JITTER_PATH, return_value=(0.0, "stage")):
        executor = await scenario.run({"messages": [HumanMessage(content=REQUEST)]}, token, lambda: token.steer(STEER))

    assert scenario.model.failed, "the scenario must really have restarted the pass"
    assert events_of(executor, AgentEventType.ERROR) == []
    assert len(scenario.model.requests) == len(turns)
    assert scenario.read_by_model(STEER)
    assert [event["data"]["count"] for event in events_of(executor, AgentEventType.STEERING)] == [1]
    assert [str(message.content) for message in await scenario.thread()].count(STEER) == 1


# ---------------------------------------------------------------------------
# The turn's last moments: accepted means delivered, anything later is refused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("resumed", [False, True], ids=["fresh", "resumed"])
async def test_a_steer_accepted_after_the_last_check_is_still_delivered(tracker: MagicMock, resumed: bool):
    """The token takes a message after every steering check has looked: the run must read it, not end over it."""
    turns = [answer("all done"), answer("citing the source")]
    if resumed:
        turns.insert(0, tool_turn("gate", {"path": "report.md"}, "g1"))
    scenario = Scenario(tracker, turns)
    first_input = {"messages": [HumanMessage(content=REQUEST)]}
    token = SteeringToken()
    accepted: list[bool] = []
    last_check = StreamExecutor._handle_goal_continuation

    async def land_after_the_checks(self: StreamExecutor, *args: object, **kwargs: object) -> bool:
        decision = await last_check(self, *args, **kwargs)
        if not accepted:
            accepted.append(token.steer(LATE_STEER))
        return decision

    if resumed:
        await scenario.run(first_input, SteeringToken())
        assert await scenario.paused_on_approval()
    with patch.object(StreamExecutor, "_handle_goal_continuation", land_after_the_checks):
        executor = await scenario.run(Command(resume="approved") if resumed else first_input, token)

    assert accepted == [True]
    assert events_of(executor, AgentEventType.ERROR) == []
    assert len(scenario.model.requests) == len(turns)
    assert scenario.read_by_model(LATE_STEER)
    assert [event["data"]["count"] for event in events_of(executor, AgentEventType.STEERING)] == [1]
    assert [str(message.content) for message in await scenario.thread()].count(LATE_STEER) == 1


@pytest.mark.asyncio
async def test_a_run_that_ended_refuses_steering_so_the_sender_keeps_the_message(tracker: MagicMock):
    scenario = Scenario(tracker, [answer("all done")])
    token = SteeringToken()

    await scenario.run({"messages": [HumanMessage(content=REQUEST)]}, token)

    assert token.steer(LATE_STEER) is False
    assert token.redirect(LATE_STEER) is False
    assert token.has_pending is False


@pytest.mark.asyncio
async def test_a_failed_attempt_leaves_its_token_open_for_the_retry(tracker: MagicMock):
    """Only a completed turn closes its token: a sub-agent whose attempt failed is retried on the same token."""
    scenario = Scenario(tracker, [answer("never reached")], fail_on=1, error="provider exploded")
    token = SteeringToken()

    with pytest.raises(MyrmLLMError, match="provider exploded"):
        await scenario.run({"messages": [HumanMessage(content=REQUEST)]}, token)

    assert token.steer(STEER) is True


# ---------------------------------------------------------------------------
# Handler: what the next input is, per kind of turn
# ---------------------------------------------------------------------------

QUESTION = HumanMessage(content="Write the Q3 report")
CUT_REPLY = AIMessage(content="Let me look at the 2023 fig")


def _steering_executor(agent_input: object, *messages: str, redirect: bool = False) -> StreamExecutor:
    token = SteeringToken()
    send = token.redirect if redirect else token.steer
    for message in messages:
        send(message)
    executor = make_executor(make_context(None, agent_input))
    executor._ctx.steering_token = token
    return executor


def _next_messages(executor: StreamExecutor) -> list[BaseMessage]:
    next_input = executor._ctx.agent_input
    assert isinstance(next_input, dict), "the re-run must be fed a plain input, never the consumed Command"
    return list(next_input["messages"])


@pytest.mark.asyncio
async def test_fresh_turn_steer_reruns_with_its_messages_and_the_steer():
    executor = _steering_executor({"messages": [QUESTION]}, STEER)
    produced = AIMessage(content="working on it")

    assert await executor._handle_steering([QUESTION, produced]) is True

    assert _next_messages(executor) == [QUESTION, produced, HumanMessage(content=STEER)]
    assert executor.streaming_final_answer is False


@pytest.mark.asyncio
async def test_resumed_turn_steer_continues_from_its_thread_with_only_the_steer():
    """The thread holds what the resumed turn produced, so the re-run carries just the steer."""
    executor = _steering_executor(Command(resume="approved"), STEER, "and keep it short")
    produced = ToolMessage(content="step 1 done", tool_call_id="w1")

    assert await executor._handle_steering([produced]) is True

    assert [message.content for message in _next_messages(executor)] == [STEER, "and keep it short"]
    assert [event["data"]["count"] for event in events_of(executor, AgentEventType.STEERING)] == [2]


@pytest.mark.asyncio
@pytest.mark.parametrize("resumed", [False, True], ids=["fresh", "resumed"])
async def test_a_steer_is_the_users_own_words_not_a_runtime_hint(resumed: bool):
    """Unlike a recovery hint, a steer carries user authority: the approval ledger and input guard read it."""
    executor = _steering_executor(Command(resume="approved") if resumed else {"messages": [QUESTION]}, STEER)

    await executor._handle_steering([] if resumed else [QUESTION])

    assert is_user_authored_human_message(_next_messages(executor)[-1]) is True


@pytest.mark.asyncio
async def test_fresh_turn_redirect_keeps_the_cut_reply_it_collected():
    executor = _steering_executor({"messages": [QUESTION]}, "no, the 2024 data", redirect=True)
    executor._redirect_partial = CUT_REPLY

    assert await executor._handle_steering([QUESTION, CUT_REPLY]) is True

    assert _next_messages(executor) == [QUESTION, CUT_REPLY, HumanMessage(content="no, the 2024 data")]
    (event,) = events_of(executor, AgentEventType.REDIRECTED)
    assert event["data"]["partial_preserved"] is True


@pytest.mark.asyncio
async def test_resumed_turn_redirect_carries_the_cut_reply_and_nothing_else():
    """Only the cut reply is missing from the thread: it never completed, so the graph never committed it."""
    executor = _steering_executor(Command(resume="approved"), "no, the 2024 data", redirect=True)
    executor._redirect_partial = CUT_REPLY
    committed = ToolMessage(content="approved:yes", tool_call_id="g1")

    assert await executor._handle_steering([committed, CUT_REPLY]) is True

    assert _next_messages(executor) == [CUT_REPLY, HumanMessage(content="no, the 2024 data")]
    (event,) = events_of(executor, AgentEventType.REDIRECTED)
    assert event["data"]["partial_preserved"] is True
    assert executor._redirect_partial is None


@pytest.mark.asyncio
async def test_redirect_with_no_cut_reply_carries_just_the_message():
    """A reply the model finished is already in the thread: the redirect reports nothing preserved."""
    executor = _steering_executor(Command(resume="approved"), "no, the 2024 data", redirect=True)

    assert await executor._handle_steering([ToolMessage(content="approved:yes", tool_call_id="g1")]) is True

    assert _next_messages(executor) == [HumanMessage(content="no, the 2024 data")]
    (event,) = events_of(executor, AgentEventType.REDIRECTED)
    assert event["data"]["partial_preserved"] is False


@pytest.mark.asyncio
async def test_a_cancelled_run_leaves_its_steering_alone():
    executor = _steering_executor(Command(resume="approved"), STEER)
    executor._ctx.stats.was_cancelled = True

    assert await executor._handle_steering([]) is False

    assert isinstance(executor._ctx.agent_input, Command)
    assert executor._ctx.steering_token is not None and executor._ctx.steering_token.has_pending
