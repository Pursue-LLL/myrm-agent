"""Model-call memo wiring for the LiteLLM async adapter.

[INPUT]
- infra.memo.call_scope::{begin_memo_call, complete_memo_call, current_llm_call_scope, fail_memo_call, start_memo_call} (POS: per-call memo ledger and scope)
- langchain_core.messages::AIMessageChunk (POS: replayable answer shape)

[OUTPUT]
- MemoRun: one model call's memo handle — `replay` when the ledger has the answer, `finish`/`fail` to record it
- memo_run(): open a handle for the given request identity
- memo_payload(): the replayable payload of a finished answer
- replay_memo_chunk(): turn a recorded payload back into a stream chunk

[POS]
Keeps the memo protocol out of the adapter mixin: the mixin only asks "do I already have an
answer, and how do I record mine", so the toolkits layer carries no ledger bookkeeping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from myrm_agent_harness.infra.memo.call_scope import (
    begin_memo_call,
    complete_memo_call,
    current_llm_call_scope,
    fail_memo_call,
    start_memo_call,
)

logger = logging.getLogger(__name__)


def memo_payload(result: Any) -> dict[str, object]:
    """The replayable payload of a finished answer.

    The answer lives in ``aggregated_response.choices[0].message``. The final chunk's message is
    stored exactly as it is, so replaying needs no conversion: the tool calls are already in the
    shape the consumer expects, and converting at replay time is where a tool call would silently
    go wrong.
    """
    aggregated = getattr(result, "aggregated_response", None) or {}
    answer: dict[str, Any] = {}
    choices = aggregated.get("choices") if isinstance(aggregated, dict) else None
    if choices and isinstance(choices[0], dict):
        raw_message = choices[0].get("message")
        if isinstance(raw_message, dict):
            answer = raw_message

    payload: dict[str, object] = {"content": str(answer.get("content") or "")}
    final_tool_chunk = getattr(result, "final_tool_chunk", None)
    if final_tool_chunk is not None:
        try:
            payload["message"] = dict(final_tool_chunk.message)
        except Exception:
            logger.debug("LLM memo: the final chunk could not be captured.", exc_info=True)
    return payload


def replay_memo_chunk(payload: dict[str, object]) -> ChatGenerationChunk | None:
    """Rebuild the chunk of a replayed answer; None when the payload cannot be replayed."""
    try:
        message = payload.get("message")
        content = str(payload.get("content") or "")
        if isinstance(message, dict):
            kwargs = {key: value for key, value in message.items() if key != "content"}
            kwargs["content"] = content or str(message.get("content") or "")
            return ChatGenerationChunk(message=AIMessageChunk(**kwargs))
        return ChatGenerationChunk(message=AIMessageChunk(content=content))
    except Exception:
        logger.warning("LLM memo: the recorded answer could not be replayed.", exc_info=True)
        return None


@dataclass(slots=True)
class MemoRun:
    """One model call's memo handle."""

    scope: Any
    attempt: Any
    model_name: str

    @property
    def replay(self) -> dict[str, object] | None:
        """The recorded answer, or None when this call has to reach the model."""
        response: dict[str, object] | None = self.attempt.response
        return response

    def begin(self) -> None:
        start_memo_call(self.scope, self.attempt, self.model_name)

    def finish(self, result: Any) -> None:
        complete_memo_call(self.scope, self.attempt, self.model_name, memo_payload(result))

    def finish_payload(self, payload: dict[str, object]) -> None:
        complete_memo_call(self.scope, self.attempt, self.model_name, payload)

    def fail(self, error: BaseException) -> None:
        fail_memo_call(self.scope, self.attempt, self.model_name, str(error))


def memo_run(model_name: str, message_dicts: list[dict[str, Any]], params: dict[str, Any]) -> MemoRun:
    """Open a memo handle for this request identity."""
    scope = current_llm_call_scope()
    attempt = begin_memo_call(scope, model_name, message_dicts, params)
    return MemoRun(scope=scope, attempt=attempt, model_name=model_name)


__all__ = [
    "MemoRun",
    "memo_payload",
    "memo_run",
    "replay_memo_chunk",
]
