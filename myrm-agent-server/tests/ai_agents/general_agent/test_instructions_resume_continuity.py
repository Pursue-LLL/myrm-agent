"""A resumed run keeps the instructions of the run it continues; a new message follows its own.

[INPUT]
- app/ai_agents/agent_middlewares/user_instructions_middleware.py (POS: source under inspection; injects <user_instructions> from the run context)

[OUTPUT]
- Tests, on a real ``create_agent`` graph with a real interrupt, that the segment after the interrupt carries the same
  instructions block as the segment before it, that the next message without instructions carries none, and that the
  next message with new instructions carries only the new ones.

[POS]
An approval or plan answer resumes the graph with a request that carries no instructions, so the run context of the
resumed segment is empty. The instructions of the interrupted run have to survive the pause in the graph state; the
next message replaces them with whatever it sends, nothing included.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from pydantic import Field

from app.ai_agents.agent_middlewares.user_instructions_middleware import user_instructions_middleware

_IDENTITY = "<identity>You are the test agent.</identity>"
_FIRST = "Always answer in French."
_SECOND = "Always answer in German."
_INSTRUCTIONS_TAG = "<user_instructions"


@tool
def ask_approval() -> str:
    """Pause the run until the user answers."""
    return str(interrupt("approve?"))


class _ScriptedModel(BaseChatModel):
    """Asks for approval on its first reply, answers "done" afterwards, and records each call's instructions blocks."""

    instruction_blocks: list[list[str]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.instruction_blocks.append(
            [str(m.content) for m in messages if isinstance(m, SystemMessage) and _INSTRUCTIONS_TAG in str(m.content)]
        )
        if len(self.instruction_blocks) == 1:
            reply = AIMessage(content="", tool_calls=[{"name": "ask_approval", "args": {}, "id": "call-1"}])
        else:
            reply = AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=reply)])


async def test_resumed_segment_keeps_the_interrupted_instructions_and_the_next_message_its_own() -> None:
    model = _ScriptedModel()
    graph = create_agent(
        model,
        tools=[ask_approval],
        middleware=[user_instructions_middleware],
        checkpointer=InMemorySaver(),
        system_prompt=_IDENTITY,
    )
    config = {"configurable": {"thread_id": "instructions-resume-continuity"}}

    await graph.ainvoke({"messages": [HumanMessage(content="go")]}, config, context={"user_instructions": _FIRST})
    await graph.ainvoke(Command(resume="approved"), config)
    await graph.ainvoke({"messages": [HumanMessage(content="next")]}, config)
    await graph.ainvoke({"messages": [HumanMessage(content="again")]}, config, context={"user_instructions": _SECOND})

    first_segment, resumed_segment, without_instructions, with_new_instructions = model.instruction_blocks
    assert len(first_segment) == 1 and _FIRST in first_segment[0], "the first segment carries the instructions"
    assert len(resumed_segment) == 1 and _FIRST in resumed_segment[0], "the resumed segment carries the same instructions"
    assert without_instructions == [], "a message that sends no instructions runs without any"
    assert len(with_new_instructions) == 1, "the next message carries exactly one block"
    assert _SECOND in with_new_instructions[0] and _FIRST not in with_new_instructions[0], "and it holds only the new text"
