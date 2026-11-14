"""The retrieval embedding helper trusts an embedding config only after a request proves it can embed."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.support import retrieval_embedding, test_secrets
from tests.support.local_embedding_server import LocalEmbeddingServer
from tests.support.retrieval_embedding import configured_retrieval_embedding, embedding_unusable_reason

_ACCOUNT_KEY = "account-key"


class _ExhaustedAccountHandler(BaseHTTPRequestHandler):
    """Answers every request the way a provider does once the account balance is used up."""

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 (http.server base class naming)
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        body = json.dumps({"code": 30001, "message": "Sorry, your account balance is insufficient"}).encode()
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def _exhausted_account() -> Iterator[str]:
    """Serve the exhausted-account answer on an ephemeral port and yield the account's ``apiBase``."""
    server = HTTPServer(("127.0.0.1", 0), _ExhaustedAccountHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def _working_account() -> Iterator[str]:
    """A local endpoint that embeds, standing in for a funded account; yields its ``apiBase``."""
    server = LocalEmbeddingServer(port=0).start()
    try:
        yield server.base_url
    finally:
        server.stop()


def _account(api_base: str) -> dict[str, str]:
    return {"model": "BAAI/bge-m3", "apiKey": _ACCOUNT_KEY, "apiBase": api_base}


def _secrets(api_base: str | None) -> dict[str, str | None]:
    """The ``.env.test`` view of an account; ``None`` means the file has no embedding key at all."""
    if api_base is None:
        return {}
    return {"EMBEDDING_API_KEY": _ACCOUNT_KEY, "EMBEDDING_BASE_URL": api_base, "EMBEDDING_MODEL": "BAAI/bge-m3"}


class _Backend:
    """The backend's ``retrieval`` setting as the helper reads and writes it."""

    def __init__(self, embedding_config: dict[str, object] | None) -> None:
        self.retrieval: dict[str, object] = {"embeddingConfig": embedding_config} if embedding_config else {}
        self.writes = 0

    def fetch(self, key: str, *, api_url: str) -> dict[str, object]:
        return dict(self.retrieval)

    def put(self, key: str, value: dict[str, object], *, api_url: str) -> None:
        self.retrieval = dict(value)
        self.writes += 1

    @property
    def embedding_config(self) -> dict[str, object]:
        config = self.retrieval.get("embeddingConfig")
        assert isinstance(config, dict)
        return config


@dataclass(frozen=True)
class _Run:
    backend: _Backend
    config_while_open: dict[str, object]
    reason_while_open: str | None


def _run(monkeypatch: pytest.MonkeyPatch, secrets: dict[str, str | None], existing: dict[str, object] | None = None) -> _Run:
    """Run the helper against a backend stub and record the config that was in force while its block was open."""
    backend = _Backend(existing)
    monkeypatch.setattr(retrieval_embedding, "fetch_config_value", backend.fetch)
    monkeypatch.setattr(retrieval_embedding, "put_config_value", backend.put)
    monkeypatch.setattr(retrieval_embedding, "load_test_secrets", lambda: test_secrets.TestSecrets(raw=secrets))
    with configured_retrieval_embedding("http://backend.invalid"):
        config = dict(backend.embedding_config)
        reason = embedding_unusable_reason(config)
    return _Run(backend=backend, config_while_open=config, reason_while_open=reason)


def test_an_account_that_can_embed_is_not_flagged() -> None:
    with _working_account() as api_base:
        assert embedding_unusable_reason(_account(api_base)) is None


def test_an_exhausted_account_is_flagged_by_its_status() -> None:
    with _exhausted_account() as api_base:
        assert embedding_unusable_reason(_account(api_base)) == "HTTP 402"


def test_an_unreachable_endpoint_is_flagged_by_its_error_type() -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    assert embedding_unusable_reason(_account(f"http://127.0.0.1:{port}/v1")) == "ConnectError"


def test_a_config_without_an_endpoint_is_not_probed() -> None:
    assert embedding_unusable_reason(_account("")) is None


def test_an_exhausted_account_makes_the_helper_use_the_local_server(monkeypatch: pytest.MonkeyPatch) -> None:
    with _exhausted_account() as api_base:
        run = _run(monkeypatch, _secrets(api_base))

    assert run.config_while_open["provider"] == "openai_compatible"
    assert run.config_while_open["apiKey"] == "test-key"
    assert str(run.config_while_open["apiBase"]).startswith("http://127.0.0.1:")
    assert run.config_while_open["apiBase"] != api_base
    assert run.reason_while_open is None


def test_an_account_that_can_embed_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    with _working_account() as api_base:
        run = _run(monkeypatch, _secrets(api_base))

    assert run.config_while_open["provider"] == "siliconflow"
    assert run.config_while_open["apiKey"] == _ACCOUNT_KEY
    assert run.config_while_open["apiBase"] == api_base


def test_without_an_account_the_local_server_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _run(monkeypatch, _secrets(None))

    assert run.config_while_open["provider"] == "openai_compatible"
    assert run.config_while_open["apiKey"] == "test-key"
    assert run.reason_while_open is None


def test_a_config_on_the_backend_that_can_embed_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    with _working_account() as api_base:
        existing: dict[str, object] = {"provider": "openai_compatible", **_account(api_base)}
        run = _run(monkeypatch, _secrets(None), existing)

    assert run.backend.writes == 0
    assert run.config_while_open == existing


def test_a_config_without_an_endpoint_on_the_backend_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    existing: dict[str, object] = {"provider": "siliconflow", "model": "BAAI/bge-m3", "apiKey": _ACCOUNT_KEY}
    run = _run(monkeypatch, _secrets(None), existing)

    assert run.backend.writes == 0
    assert run.config_while_open == existing


def test_an_exhausted_config_on_the_backend_is_replaced_for_the_block_and_put_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stack seeds the ``.env.test`` account into a fresh runtime, so the dead config is usually already there."""
    with _exhausted_account() as api_base:
        existing: dict[str, object] = {"provider": "siliconflow", **_account(api_base)}
        run = _run(monkeypatch, _secrets(api_base), existing)

    assert run.config_while_open["provider"] == "openai_compatible"
    assert run.reason_while_open is None
    assert run.backend.embedding_config == existing
