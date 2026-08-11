"""Local OpenAI-compatible embedding server for E2E tests.

[SCOPE]
A minimal, deterministic ``/v1/embeddings`` endpoint that stands in for an
external embedding provider. The product accepts any OpenAI-compatible
``api_base`` (including self-hosted endpoints), so pointing the WebUI
retrieval config at this server is a real product usage, not a code path
bypass. Deterministic hash vectors keep memory retrieval reproducible with
zero external credentials — useful when test accounts for cloud embedding
providers are unavailable (e.g. quota exhausted).

[USAGE]
    from tests.support.local_embedding_server import LocalEmbeddingServer

    server = LocalEmbeddingServer(port=8399)
    server.start()
    # configure retrieval.embeddingConfig -> apiBase=http://127.0.0.1:8399/v1
    server.stop()

[CONTRACT]
- POST /v1/embeddings accepts OpenAI ``input`` list and returns OpenAI-shaped
  ``{"data": [{"object": "embedding", "index", "embedding"}], ...}``.
- GET /v1/models returns a model list (litellm compatibility).
- Vectors are 1024-dimensional (same as ``BAAI/bge-m3``) and deterministic
  per input text, so cosine search behaves stably across reruns.
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

DEFAULT_DIMENSION = 1024
DEFAULT_MODEL = "test-embed-v1"


def deterministic_vector(text: str, dimension: int = DEFAULT_DIMENSION) -> list[float]:
    """Deterministic pseudo-random unit-scale vector in [-1, 1] per text."""
    seed = hashlib.sha256(text.encode("utf-8")).hexdigest()
    vector: list[float] = []
    for i in range(dimension):
        digest = hashlib.sha256(f"{seed}:{i}".encode("utf-8")).hexdigest()
        value = int(digest[:8], 16) / 0xFFFFFFFF
        vector.append(round(value * 2.0 - 1.0, 6))
    return vector


class _EmbeddingHandler(BaseHTTPRequestHandler):
    _model = DEFAULT_MODEL
    _dimension = DEFAULT_DIMENSION

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server base class naming)
        if self.path.rstrip("/") == "/v1/models":
            self._send_json(
                {
                    "object": "list",
                    "data": [{"id": self._model, "object": "model"}],
                }
            )
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) or b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, status=400)
            return

        texts = payload.get("input") or payload.get("texts")
        if not isinstance(texts, list):
            self._send_json({"error": "missing input list"}, status=400)
            return

        data = [
            {
                "object": "embedding",
                "index": index,
                "embedding": deterministic_vector(str(text), self._dimension),
            }
            for index, text in enumerate(texts)
        ]
        self._send_json(
            {
                "object": "list",
                "data": data,
                "model": self._model,
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }
        )


class LocalEmbeddingServer:
    """Thread-backed OpenAI-compatible embedding endpoint."""

    def __init__(self, port: int = 8399, model: str = DEFAULT_MODEL) -> None:
        self.port = port
        self.model = model
        self.base_url = f"http://127.0.0.1:{port}/v1"
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "LocalEmbeddingServer":
        _EmbeddingHandler._model = self.model
        self._server = HTTPServer(("127.0.0.1", self.port), _EmbeddingHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="local-embedding-server"
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
