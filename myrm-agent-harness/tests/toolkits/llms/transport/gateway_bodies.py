"""Chat-completion answers as a gateway sends them, and the model that reads them, for the full-path replay tests."""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.llms.core.llm import TransportChatModel, create_chat_model
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker

Body = dict[str, object]
USAGE: Body = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
STRING_USAGE: Body = {"prompt_tokens": "11", "completion_tokens": "7", "total_tokens": "18"}
CALL: Body = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'},
}
TOOL_MESSAGE: Body = {"content": None, "tool_calls": [CALL]}


def answer(message: Body | None = None, finish: object = "stop", **top: object) -> Body:
    """One chat.completion that says "hello"; ``message`` overrides fields of the message, ``top`` of the answer."""
    message_fields: Body = {"role": "assistant", "content": "hello", **(message or {})}
    choice: Body = {"index": 0, "message": message_fields, "finish_reason": finish}
    return {"id": "c1", "object": "chat.completion", "model": "m", "choices": [choice], "usage": dict(USAGE), **top}


def chunk(delta: Body | None = None, finish: object = None, **top: object) -> Body:
    choice: Body = {"index": 0, "delta": delta if delta is not None else {}, "finish_reason": finish}
    return {"id": "c1", "object": "chat.completion.chunk", "model": "m", "choices": [choice], **top}


def usage_only(usage: object, **top: object) -> Body:
    return {"id": "c1", "choices": [], "usage": usage, **top}


def failed_choice(error: Body) -> Body:
    """OpenRouter's way to fail an answer whose upstream broke: the ``error`` finish reason and the detail on the choice."""
    body = answer({"content": ""}, finish="error")
    body["choices"][0]["error"] = error  # type: ignore[index]
    return body


def sse_body(*frames: Body | str) -> bytes:
    lines = [f"data: {frame if isinstance(frame, str) else json.dumps(frame)}\n\n" for frame in frames]
    return "".join([*lines, "data: [DONE]\n\n"]).encode()


def chat_model(*, streaming: bool) -> TransportChatModel:
    return create_chat_model(
        model="openai/gpt-4o-mini", base_url="http://gateway.test/v1", api_key="k", temperature=0.0, streaming=streaming
    )


def usage_of(tracker: TokenTracker) -> tuple[int, int, int] | None:
    """What the accounting recorded for the call; ``None`` when the call left no usage event."""
    if tracker.call_count == 0:
        return None
    usage = tracker.usage
    return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens
