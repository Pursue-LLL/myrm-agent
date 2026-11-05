"""Wire-level chat-completions provider on loopback that serves exactly one API key.

[INPUT]
- `accepted_key`: the bearer token the provider answers; any other key is refused with 401

[OUTPUT]
- FakeChatProvider: serves POST {base_url}/chat/completions, streaming and not, and records every call in `requests`
- ChatRequest: path, Authorization header, lower-cased request headers and JSON body of one call
- fake_chat_provider(): context manager running one provider on an ephemeral loopback port

[POS]
真实 ChatLiteLLM（LiteLLM + OpenAI SDK）打到的假上游：LLM 探针类测试用它代替对 get_llm 的 patch，
某个 Key 或端点有没有真的被问到，由 `requests` 里的记录证明，而不是由返回值猜。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

_REFUSAL = {"error": {"message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}}


@dataclass(frozen=True)
class ChatRequest:
    path: str
    authorization: str | None
    headers: dict[str, str]
    body: dict[str, object]


class FakeChatProvider:
    """Answers `pong` to the bearer token `accepted_key` and refuses every other key with an OpenAI-style 401."""

    def __init__(self, accepted_key: str) -> None:
        self.accepted_key = accepted_key
        self.requests: list[ChatRequest] = []
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def answer(self, request: ChatRequest) -> tuple[int, str, bytes]:
        """Status, content type and body for one call."""
        if request.authorization != f"Bearer {self.accepted_key}":
            return 401, "application/json", json.dumps(_REFUSAL).encode()
        model = request.body.get("model")
        if request.body.get("stream"):
            chunks = [
                {
                    "id": "c1",
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [self._choice({"role": "assistant", "content": "pong"}, None)],
                },
                {"id": "c1", "object": "chat.completion.chunk", "model": model, "choices": [self._choice({}, "stop")]},
            ]
            events = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            return 200, "text/event-stream", events.encode()
        completion = {
            "id": "c1",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        return 200, "application/json", json.dumps(completion).encode()

    @staticmethod
    def _choice(delta: dict[str, str], finish_reason: str | None) -> dict[str, object]:
        return {"index": 0, "delta": delta, "finish_reason": finish_reason}

    def start(self) -> None:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request = ChatRequest(
                    self.path,
                    self.headers.get("Authorization"),
                    {name.lower(): value for name, value in self.headers.items()},
                    json.loads(self.rfile.read(length) or b"{}"),
                )
                provider.requests.append(request)
                status, content_type, payload = provider.answer(request)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                pass

        return Handler


@contextmanager
def fake_chat_provider(accepted_key: str) -> Iterator[FakeChatProvider]:
    provider = FakeChatProvider(accepted_key)
    provider.start()
    try:
        yield provider
    finally:
        provider.close()
