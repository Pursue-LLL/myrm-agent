"""Re-driving a turn from its thread: the input every "append a hint and run again" recovery hands back.

[INPUT]
- core.message_origin::runtime_human_message (POS: a hint the runtime wrote, which user-input screens skip)
- langgraph.types::Command (POS: the one-shot input of a turn resumed after an approval)

[OUTPUT]
- StreamRedriveMixin: `_redrive_with_hint` replaces the next input of the turn with the messages to run again plus one runtime-authored hint.

[POS]
Shared by the truncation and empty-response recoveries, which differ in when they fire and what they say but all
re-run the turn the same way. Keeping that way here makes fresh and resumed turns recover identically by
construction.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, cast

from langgraph.types import Command

from myrm_agent_harness.core.message_origin import runtime_human_message

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage, BaseMessage

    from myrm_agent_harness.agent.streaming.stream_executor import StreamContext


class StreamRedriveMixin:
    _ctx: StreamContext
    streaming_final_answer: bool

    def _redrive_with_hint(self, kept: Iterable[BaseMessage], hint: str) -> None:
        """Make the next ``astream`` run the turn again with ``kept`` followed by ``hint``.

        A fresh turn's input holds the messages the turn started from, so it is rebuilt from ``kept``. A resumed
        turn's input is a ``Command`` LangGraph has already consumed: feeding it to a graph that has run to its end
        advances nothing. Its thread (checkpoint) holds every message the turn produced, so the re-run is a
        continue-mode input that carries only the hint and leaves the prefix the provider caches untouched.

        The failed reply stays in the thread either way; the dangling-call middleware answers a withheld call with an
        invalid-arguments result, so the model reads what went wrong before it reads the hint.
        """
        ctx = self._ctx
        if isinstance(ctx.agent_input, Command):
            ctx.agent_input = {"messages": []}
            kept = ()
        carried = tuple(kept)
        messages_dict = ctx.agent_input
        messages = cast("list[BaseMessage]", messages_dict.get("messages", []))
        messages.clear()
        messages.extend(carried)
        messages.append(runtime_human_message(hint))
        messages_dict["messages"] = cast("list[AnyMessage]", messages)
        self.streaming_final_answer = False
