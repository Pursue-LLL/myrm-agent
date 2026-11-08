"""Canned, valid provider answers for the golden capture: one per protocol a request can address.

[INPUT]
- event_stream_bodies (POS: the AWS event-stream answers of the Converse wire)
- httpx (POS: the request being answered and the response built for it)

[OUTPUT]
- canned_answer: a valid answer, streamed or whole, in the protocol the request addresses

[POS]
The recorded request is all the golden comparison looks at, so an answer only has to be well-formed for the wire that
sent it: chat completions, Responses, Anthropic Messages, Gemini, Ollama chat and Bedrock Converse.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import httpx

from .event_stream_bodies import CONTENT_TYPE as EVENT_STREAM
from .event_stream_bodies import converse_answer, text_stream

_CHAT_JSON = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "m",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
}
_CHAT_SSE = (
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m","choices":[{"index":0,"delta":{"role":"assistant","content":"ok"},"finish_reason":null}]}\n\n'
    'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"m","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}\n\n'
    "data: [DONE]\n\n"
)
_ANTHROPIC_JSON = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "m",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 3, "output_tokens": 1},
}
_ANTHROPIC_SSE = (
    'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","model":"m","content":[],"stop_reason":null,"usage":{"input_tokens":3,"output_tokens":1}}}\n\n'
    'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
    'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n\n'
    'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'
    'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n'
    'event: message_stop\ndata: {"type":"message_stop"}\n\n'
)
_GEMINI_JSON = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP", "index": 0}],
    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1, "totalTokenCount": 4},
}
_OLLAMA_CHAT_NDJSON = (
    '{"model":"m","created_at":"2024-01-01T00:00:00Z","message":{"role":"assistant","content":"ok"},'
    '"done":true,"prompt_eval_count":3,"eval_count":1}\n'
)
_RESPONSES_JSON = {
    "id": "resp_1",
    "object": "response",
    "created_at": 1,
    "status": "completed",
    "model": "m",
    "output": [
        {
            "type": "message",
            "id": "msg_1",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "ok", "annotations": []}],
        }
    ],
    "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
}
_RESPONSES_SSE = (
    "event: response.output_text.delta\ndata: "
    + json.dumps(
        {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": "ok"}
    )
    + "\n\n"
    "event: response.completed\ndata: "
    + json.dumps({"type": "response.completed", "response": _RESPONSES_JSON})
    + "\n\n"
)


def canned_answer(request: httpx.Request) -> httpx.Response:
    """A valid answer in the protocol the request addresses."""
    path = urlsplit(str(request.url)).path
    try:
        body = json.loads(request.content or b"{}")
    except ValueError:
        body = {}
    stream = bool(body.get("stream")) or "streamGenerateContent" in path
    sse = {"content-type": "text/event-stream"}
    plain = {"content-type": "application/json"}

    def answer(streamed: str, whole: object) -> httpx.Response:
        return httpx.Response(
            200,
            content=streamed if stream else json.dumps(whole),
            headers=sse if stream else plain,
            request=request,
        )

    if path.endswith("/responses"):
        return answer(_RESPONSES_SSE, _RESPONSES_JSON)
    if path.endswith("/messages") and ("anthropic-version" in request.headers or "x-api-key" in request.headers):
        return answer(_ANTHROPIC_SSE, _ANTHROPIC_JSON)
    if "generateContent" in path or "streamGenerateContent" in path:
        return answer(f"data: {json.dumps(_GEMINI_JSON)}\n\n", _GEMINI_JSON)
    if path.endswith("/api/chat"):
        return httpx.Response(
            200, content=_OLLAMA_CHAT_NDJSON, headers={"content-type": "application/x-ndjson"}, request=request
        )
    if path.endswith("/converse"):
        return httpx.Response(200, json=converse_answer({"text": "ok"}), request=request)
    if path.endswith("/converse-stream"):
        content = b"".join(text_stream("ok"))
        return httpx.Response(200, content=content, headers={"content-type": EVENT_STREAM}, request=request)
    return answer(_CHAT_SSE, _CHAT_JSON)
