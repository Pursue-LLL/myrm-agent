"""Harness that drives the real ``create_agent`` loop through ``StreamExecutor.execute()`` with scripted model turns.

A ``ScriptedModel`` plays one prepared generation per call (an unscripted extra call fails the test loudly), the
file-writing tool can be gated behind an approval pause, and ``run_agent`` answers every pause with
``Command(resume=...)`` exactly as a resumed turn does in the product, so recovery is exercised on fresh and on
resumed turns alike.
"""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import ConfigDict, Field

from myrm_agent_harness.agent.middlewares.tooling.dangling_tool_call_middleware import dangling_tool_call_middleware
from myrm_agent_harness.agent.streaming.stream_executor import StreamContext, StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.llms.adapters.tool_recovery import build_final_tool_call_chunk
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import get_ephemeral_max_output_tokens

BASE_MAX_TOKENS = 1_000
FULL_REPORT = "# Q3 report\n\nRevenue grew by 12%.\n"
# ``content`` is cut inside its string value, as an output-length limit does.
CUT_ARGUMENTS = '{"path": "report.md", "content": "# Q3 report\\n\\nRevenue grew by 1'
TRACKER_PATH = "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker"
THREAD_ID = "scripted-thread"
MAX_RESUMES = 4

Turn = tuple[AIMessage, str]
"""One scripted model generation: the final AI message and the provider's finish_reason."""


@dataclass(frozen=True)
class Request:
    """What one model call received."""

    max_tokens: int
    messages: tuple[tuple[str, str], ...]  # (message class name, content)


class ScriptedModel(BaseChatModel):
    """Plays one scripted turn per call; an unscripted extra call fails the test loudly."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    turns: list[Turn]
    tracker: MagicMock
    requests: list[Request] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> "ScriptedModel":
        return self

    def _respond(self, messages: list[BaseMessage]) -> ChatResult:
        call_number = len(self.requests) + 1
        self.requests.append(
            Request(
                max_tokens=get_ephemeral_max_output_tokens() or BASE_MAX_TOKENS,
                messages=tuple((type(m).__name__, str(m.content)) for m in messages),
            )
        )
        if call_number > len(self.turns):
            raise AssertionError(f"unscripted model call #{call_number}")
        message, finish_reason = self.turns[call_number - 1]
        # The real adapter records the provider's finish_reason on the token tracker.
        self.tracker.last_finish_reason = finish_reason
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        return self._respond(messages)

    async def _agenerate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        return self._respond(messages)


class RecordingCompactor:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def put(self, event: object) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass

    @property
    def status_events(self) -> list[dict[str, object]]:
        return [event for event in self.events if isinstance(event, dict) and event.get("step_key")]

    @property
    def steps(self) -> list[str]:
        return [str(event["step_key"]) for event in self.status_events]


@dataclass
class Run:
    requests: list[Request]
    executed: list[tuple[str, str]]
    compactor: RecordingCompactor
    error: Exception | None
    approvals: int = 0
    """Approval pauses the flow answered with ``Command(resume=...)``."""

    @property
    def truncation_steps(self) -> list[str]:
        return [step for step in self.compactor.steps if step in ("tool_call_retry", "tool_call_truncated")]


def adapter_message(raw_calls: list[dict[str, object]], *, stream_complete: bool | None) -> AIMessage:
    """The final message the chat adapter builds for ``raw_calls`` (withheld calls only in metadata)."""
    chunk, _, _ = build_final_tool_call_chunk(raw_calls, None, stream_complete=stream_complete)
    assert chunk is not None
    return AIMessage(
        content="",
        tool_calls=list(chunk.message.tool_calls),
        additional_kwargs=dict(chunk.message.additional_kwargs),
    )


def raw_write(call_id: str, arguments: str) -> dict[str, object]:
    return {"id": call_id, "type": "function", "function": {"name": "write_file", "arguments": arguments}}


def withheld_message(arguments: str = CUT_ARGUMENTS, *, stream_complete: bool | None = False) -> AIMessage:
    message = adapter_message([raw_write("call_cut", arguments)], stream_complete=stream_complete)
    assert message.tool_calls == []
    return message


def complete_write(call_id: str = "call_ok") -> Turn:
    call = {"name": "write_file", "args": {"path": "report.md", "content": FULL_REPORT}, "id": call_id}
    return AIMessage(content="", tool_calls=[call]), "tool_calls"


def final_answer() -> Turn:
    return AIMessage(content="Done: report.md written."), "stop"


def make_context(agent: object, agent_input: object, *, thread_id: str | None = None) -> StreamContext:
    run_config: dict[str, object] = {"recursion_limit": 12}
    if thread_id is not None:
        run_config["configurable"] = {"thread_id": thread_id}
    ctx = StreamContext(
        agent=agent,
        agent_input=agent_input,
        merged_context={"locale": "en"},
        run_config=run_config,
        stats=AgentRunStatistics(),
        message_id="msg",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )
    ctx.llm = MagicMock(max_tokens=BASE_MAX_TOKENS, model_kwargs={}, model_name="scripted-model")
    return ctx


def make_executor(ctx: StreamContext) -> StreamExecutor:
    executor = StreamExecutor(ctx=ctx, fallback_llm=None, safety_fallback_llm=None, rebuild_agent_fn=MagicMock())
    executor._compactor = RecordingCompactor()
    return executor


async def _has_pending_pause(agent: CompiledStateGraph) -> bool:
    snapshot = await agent.aget_state({"configurable": {"thread_id": THREAD_ID}})
    return bool(snapshot.interrupts)


async def run_agent(turns: list[Turn], *, gated: bool = False) -> tuple[Run, ScriptedModel]:
    """Run the real agent loop and executor against the scripted turns.

    With ``gated`` the file-writing tool pauses for approval before every write; each pause is answered with a
    resumed turn (a ``Command`` input on the same thread), whose executor is the one recovery runs inside.
    """
    executed: list[tuple[str, str]] = []

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a file."""
        if gated:
            interrupt({"path": path})
        executed.append((path, content))
        return f"wrote {path}"

    tracker = MagicMock(last_finish_reason=None, usage=None, total_cost_usd=0.0)
    model = ScriptedModel(turns=turns, tracker=tracker)
    tools: list[BaseTool] = [write_file]
    agent = create_agent(
        model=model, tools=tools, middleware=[dangling_tool_call_middleware], checkpointer=InMemorySaver()
    )

    error: Exception | None = None
    approvals = 0
    agent_input: object = {"messages": [HumanMessage(content="Write the Q3 report to report.md")]}
    compactors: list[RecordingCompactor] = []
    with (
        patch("myrm_agent_harness.agent.hooks.executor.fire_hook", new_callable=AsyncMock),
        patch(TRACKER_PATH, return_value=tracker),
    ):
        while True:
            executor = make_executor(make_context(agent, agent_input, thread_id=THREAD_ID))
            assert isinstance(executor._compactor, RecordingCompactor)
            compactors.append(executor._compactor)
            try:
                await executor.execute()
            except Exception as exc:
                error = exc
                break
            if approvals >= MAX_RESUMES or not await _has_pending_pause(agent):
                break
            approvals += 1
            agent_input = Command(resume="approved")

    merged = RecordingCompactor()
    for compactor in compactors:
        merged.events.extend(compactor.events)
    return Run(requests=model.requests, executed=executed, compactor=merged, error=error, approvals=approvals), model
