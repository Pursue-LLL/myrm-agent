"""@input: http.server, json, threading (stdlib)
@output: ChatRequest, Reply, ScriptedOpenAIEndpoint
@pos: [T] localhost OpenAI-compatible endpoint whose replies a test scripts, so a real agent runs against a deterministic model.
"""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_EMBEDDING_DIM = 1536
_MODEL = "scripted-model"


@dataclass(frozen=True)
class ChatRequest:
    """What the scripted model is asked: the conversation so far and the tools the agent offers."""

    messages: list[dict[str, object]]
    tool_names: frozenset[str]

    @property
    def last_user_text(self) -> str:
        for message in reversed(self.messages):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return ""


@dataclass(frozen=True)
class Reply:
    """Either an answer (``text``) or one tool call (``tool_name`` with ``tool_args``)."""

    text: str = ""
    tool_name: str = ""
    tool_args: dict[str, object] = field(default_factory=dict)


Script = Callable[[ChatRequest], Reply]


def _chat_request(body: dict[str, object]) -> ChatRequest:
    raw_messages = body.get("messages")
    raw_tools = body.get("tools")
    tool_names = {
        function["name"]
        for tool in (raw_tools if isinstance(raw_tools, list) else [])
        if isinstance(tool, dict) and isinstance(function := tool.get("function"), dict) and "name" in function
    }
    return ChatRequest(
        messages=[m for m in (raw_messages if isinstance(raw_messages, list) else []) if isinstance(m, dict)],
        tool_names=frozenset(str(name) for name in tool_names),
    )


class ScriptedOpenAIEndpoint:
    """``/v1/chat/completions`` (stream and not) and ``/v1/embeddings``, answering as the script says."""

    def __init__(self, script: Script) -> None:
        self._script = script
        self._call_ids = itertools.count(1)
        self.requests: list[ChatRequest] = []
        endpoint = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path.endswith("/embeddings"):
                    self._send_json(endpoint._embeddings(body))
                elif self.path.endswith("/chat/completions"):
                    endpoint._chat(self, body)
                else:
                    self._send_json({"error": "unsupported"}, status=404)

            def _send_json(self, payload: dict[str, object], *, status: int = 200) -> None:
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @staticmethod
    def _embeddings(body: dict[str, object]) -> dict[str, object]:
        raw = body.get("input")
        count = len(raw) if isinstance(raw, list) else 1
        data = [{"object": "embedding", "index": i, "embedding": [0.0] * _EMBEDDING_DIM} for i in range(count)]
        return {"object": "list", "data": data, "model": _MODEL, "usage": {"prompt_tokens": 1, "total_tokens": 1}}

    def _chat(self, handler: BaseHTTPRequestHandler, body: dict[str, object]) -> None:
        request = _chat_request(body)
        self.requests.append(request)
        reply = self._script(request)
        tool_call = (
            {
                "id": f"call_{next(self._call_ids)}",
                "type": "function",
                "function": {"name": reply.tool_name, "arguments": json.dumps(reply.tool_args)},
            }
            if reply.tool_name
            else None
        )
        finish = "tool_calls" if tool_call else "stop"
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        base: dict[str, object] = {"id": "chatcmpl-scripted", "created": 0, "model": _MODEL}
        if not body.get("stream"):
            message: dict[str, object] = {"role": "assistant", "content": None if tool_call else reply.text}
            if tool_call:
                message["tool_calls"] = [tool_call]
            payload = {**base, "object": "chat.completion", "usage": usage}
            payload["choices"] = [{"index": 0, "message": message, "finish_reason": finish}]
            handler.send_response(200)
            raw = json.dumps(payload).encode()
            handler.send_header("content-type", "application/json")
            handler.send_header("content-length", str(len(raw)))
            handler.end_headers()
            handler.wfile.write(raw)
            return
        delta: dict[str, object] = {"role": "assistant", "content": None if tool_call else reply.text}
        if tool_call:
            delta["tool_calls"] = [{"index": 0, **tool_call}]
        chunks: list[dict[str, object]] = [
            {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
            {"choices": [], "usage": usage},
        ]
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.end_headers()
        for chunk in chunks:
            handler.wfile.write(f"data: {json.dumps({**base, 'object': 'chat.completion.chunk', **chunk})}\n\n".encode())
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()
