"""Wire-level embedding and rerank provider on loopback.

[INPUT]
- `status`, `refusal`, `dimension` and `rerank_results` of the provider: what it answers to the next call

[OUTPUT]
- FakeRetrievalProvider: serves POST {api_base}/embeddings, POST {api_base}/embed (Cohere's own shape) and POST {api_base}/rerank, every call lands in `requests`
- ProviderRequest: path, Authorization header and JSON body of one call
- fake_retrieval_provider(): context manager running one provider on an ephemeral loopback port
- unreachable_api_base(): an api_base nothing listens on

[POS]
真实 CloudEmbedding 与 CloudReranker（harness 自带的 httpx 传输）打到的假上游：校验类测试用它代替对客户端类的 patch，
失败分类走的就是客户端真实抛出的异常类型。
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

# What a provider says when it refuses a call; the 401 body repeats the key, as some real providers do.
_REFUSALS = {
    401: "Incorrect API key provided: {key}",
    402: "Payment required: your account balance is insufficient",
    403: "Access denied for key {key}",
    404: "The model `{model}` does not exist",
    429: "Rate limit reached for requests",
}
_FAILURE = "The server had an error while processing your request"


@dataclass(frozen=True)
class ProviderRequest:
    path: str
    authorization: str | None
    body: dict[str, object]


class FakeRetrievalProvider:
    """Answers every call with `status`: 200 is a valid embedding / rerank response, anything else an OpenAI-style error.

    `refusal` replaces the error text a status comes with by default.
    """

    def __init__(self) -> None:
        self.status = 200
        self.refusal: str | None = None
        self.dimension = 4
        self.rerank_results: list[dict[str, float]] = [{"index": 1, "relevance_score": 0.9}]
        self.requests: list[ProviderRequest] = []
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())

    @property
    def api_base(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def answer(self, request: ProviderRequest) -> tuple[int, dict[str, object]]:
        if self.status != 200:
            key = (request.authorization or "").removeprefix("Bearer ")
            text = self.refusal or _REFUSALS.get(self.status, _FAILURE).format(key=key, model=request.body.get("model"))
            return self.status, {"error": {"message": text, "type": "invalid_request_error", "code": str(self.status)}}
        if request.path.endswith("/embed"):
            return 200, {"embeddings": {"float": [[0.1] * self.dimension]}}
        if request.path.endswith("/embeddings"):
            vector = [0.1] * self.dimension
            return 200, {
                "object": "list",
                "model": request.body.get("model"),
                "data": [{"object": "embedding", "index": 0, "embedding": vector}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }
        return 200, {"results": self.rerank_results}

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
                request = ProviderRequest(
                    self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length) or b"{}")
                )
                provider.requests.append(request)
                status, payload = provider.answer(request)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                pass

        return Handler


@contextmanager
def fake_retrieval_provider() -> Iterator[FakeRetrievalProvider]:
    provider = FakeRetrievalProvider()
    provider.start()
    try:
        yield provider
    finally:
        provider.close()


def unreachable_api_base() -> str:
    """An api_base whose port was free a moment ago, so connecting to it is refused at once."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}/v1"
