"""The retrieval embedding helper trusts an embedding config only after the product's own embedding call proves it embeds."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import pytest

from tests.support import retrieval_embedding, test_secrets
from tests.support.retrieval_embedding import (
    _PROBE_BURST,
    configured_retrieval_embedding,
    embedding_unusable_reason,
)

_KEY = "account-key"
_VOYAGE_KEY = "voyage-key"
# What a Voyage organisation without a payment method is allowed per minute.
_QUOTA_PER_MINUTE = 3


def _alive(_request_number: int) -> int:
    return 200


def _exhausted(_request_number: int) -> int:
    return 402


def _throttled(request_number: int) -> int:
    return 200 if request_number <= _QUOTA_PER_MINUTE else 429


class _Upstream(ThreadingHTTPServer):
    """An OpenAI-shaped ``/v1/embeddings`` endpoint whose status is scripted by request number."""

    daemon_threads = True

    def __init__(self, status_of: Callable[[int], int], delay_sec: float = 0.0) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.status_of = status_of
        self.delay_sec = delay_sec
        self.requests = 0
        self.last_body: dict[str, object] = {}
        self.last_authorization = ""
        self.lock = threading.Lock()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 (http.server base class naming)
        upstream = cast(_Upstream, self.server)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or b"{}")
        with upstream.lock:
            upstream.requests += 1
            status = upstream.status_of(upstream.requests)
            upstream.last_body = body
            upstream.last_authorization = self.headers.get("Authorization", "")
        time.sleep(upstream.delay_sec)
        if status == 200:
            payload: dict[str, object] = {
                "data": [{"index": i, "embedding": [0.1, 0.2, 0.3]} for i in range(len(body.get("input", [])))]
            }
        elif status == 402:
            payload = {"code": 30001, "message": "Sorry, your account balance is insufficient"}
        else:
            payload = {"detail": "reduced rate limits"}
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextmanager
def _upstream(status_of: Callable[[int], int], delay_sec: float = 0.0) -> Iterator[_Upstream]:
    server = _Upstream(status_of, delay_sec)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _account_at(api_base: str) -> dict[str, str]:
    """A custom-endpoint account as the settings page stores it."""
    return {"provider": "openai_compatible", "model": "BAAI/bge-m3", "apiKey": _KEY, "apiBase": api_base}


def _voyage_account() -> dict[str, str]:
    """Voyage as the settings page stores it: no endpoint, the provider's own is built in."""
    return {"provider": "voyage", "model": "voyage-4-lite", "apiKey": _VOYAGE_KEY}


def _secrets(primary: _Upstream | None = None, *, voyage: bool = False) -> dict[str, str | None]:
    """The ``.env.test`` view: an ``EMBEDDING_*`` account on ``primary`` and, if ``voyage``, the Voyage backup."""
    secrets: dict[str, str | None] = {}
    if primary is not None:
        secrets.update(EMBEDDING_API_KEY=_KEY, EMBEDDING_MODEL="BAAI/bge-m3", EMBEDDING_BASE_URL=primary.base)
    if voyage:
        secrets.update(VOYAGE_API_KEY=_VOYAGE_KEY, VOYAGE_EMBEDDING_MODEL="voyage/voyage-4-lite")
    return secrets


class _Backend:
    """The backend's ``retrieval`` setting as the helper reads and writes it."""

    def __init__(self, embedding_config: dict[str, str] | None) -> None:
        self.retrieval: dict[str, object] = (
            {"embeddingApplied": True, "embeddingConfig": embedding_config} if embedding_config else {}
        )
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


def _run(
    monkeypatch: pytest.MonkeyPatch,
    secrets: dict[str, str | None],
    existing: dict[str, str] | None = None,
    voyage_base: str | None = None,
) -> _Run:
    """Run the helper against a backend stub and record the config that was in force while its block was open."""
    backend = _Backend(existing)
    monkeypatch.setattr(retrieval_embedding, "fetch_config_value", backend.fetch)
    monkeypatch.setattr(retrieval_embedding, "put_config_value", backend.put)
    monkeypatch.setattr(retrieval_embedding, "load_test_secrets", lambda: test_secrets.TestSecrets(raw=secrets))
    if voyage_base is not None:
        monkeypatch.setenv("VOYAGE_API_BASE", voyage_base)
    with configured_retrieval_embedding("http://backend.invalid"):
        config = dict(backend.embedding_config)
        reason = embedding_unusable_reason(config)
    return _Run(backend=backend, config_while_open=config, reason_while_open=reason)


def test_an_account_that_can_embed_is_not_flagged() -> None:
    with _upstream(_alive) as upstream:
        assert embedding_unusable_reason(_account_at(upstream.base)) is None
        assert upstream.requests == _PROBE_BURST


def test_an_exhausted_account_is_flagged_by_its_status() -> None:
    with _upstream(_exhausted) as upstream:
        assert embedding_unusable_reason(_account_at(upstream.base)) == "HTTP 402"


def test_an_account_with_a_per_minute_quota_is_flagged_by_the_burst() -> None:
    """One request would pass: the account only fails once the quota of a minute is spent."""
    with _upstream(_throttled) as upstream:
        assert embedding_unusable_reason(_account_at(upstream.base)) == "HTTP 429"


def test_an_unreachable_endpoint_is_flagged_by_its_error_type() -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    assert embedding_unusable_reason(_account_at(f"http://127.0.0.1:{port}/v1")) == "ConnectError"


def test_an_endpoint_that_hangs_is_flagged_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retrieval_embedding, "_PROBE_TIMEOUT_SEC", 0.3)
    with _upstream(_alive, delay_sec=2.0) as upstream:
        assert embedding_unusable_reason(_account_at(upstream.base)) == "TimeoutError"


def test_a_config_without_a_key_is_flagged() -> None:
    assert embedding_unusable_reason({"provider": "voyage", "model": "voyage-4-lite"}) == "incomplete config"


def test_a_provider_with_a_built_in_endpoint_is_probed_the_way_the_product_reaches_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint is not in the config, so only the product's own routing knows where Voyage is and what it accepts."""
    with _upstream(_alive) as upstream:
        monkeypatch.setenv("VOYAGE_API_BASE", upstream.base)
        assert embedding_unusable_reason(_voyage_account()) is None
        assert upstream.last_body["model"] == "voyage-4-lite"
        assert "encoding_format" not in upstream.last_body
        assert upstream.last_authorization == f"Bearer {_VOYAGE_KEY}"

    with _upstream(_exhausted) as upstream:
        monkeypatch.setenv("VOYAGE_API_BASE", upstream.base)
        assert embedding_unusable_reason(_voyage_account()) == "HTTP 402"


def test_a_seeded_account_that_can_embed_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    with _upstream(_alive) as upstream:
        existing = _account_at(upstream.base)
        run = _run(monkeypatch, _secrets(upstream, voyage=True), existing)

    assert run.backend.writes == 0
    assert run.config_while_open == existing


def test_an_exhausted_seeded_account_gives_way_to_the_voyage_backup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with _upstream(_exhausted) as seeded, _upstream(_alive) as voyage:
        existing = _account_at(seeded.base)
        run = _run(monkeypatch, _secrets(seeded, voyage=True), existing, voyage_base=voyage.base)

        assert run.config_while_open == _voyage_account()
        assert run.reason_while_open is None
        assert run.backend.embedding_config == existing
        assert seeded.requests == _PROBE_BURST, "the seeded account is the EMBEDDING_* account and is probed once"
    assert "voyage backup in use (seeded account: HTTP 402)" in capsys.readouterr().out


@pytest.mark.parametrize("backup_status", [_exhausted, _throttled], ids=["exhausted", "throttled"])
def test_a_voyage_backup_that_cannot_serve_the_chain_gives_way_to_the_local_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], backup_status: Callable[[int], int]
) -> None:
    with _upstream(_exhausted) as seeded, _upstream(backup_status) as voyage:
        existing = _account_at(seeded.base)
        run = _run(monkeypatch, _secrets(seeded, voyage=True), existing, voyage_base=voyage.base)

    assert run.config_while_open["provider"] == "openai_compatible"
    assert run.config_while_open["apiKey"] == "test-key"
    assert str(run.config_while_open["apiBase"]).startswith("http://127.0.0.1:")
    assert run.config_while_open["apiBase"] not in {seeded.base, voyage.base}
    assert run.reason_while_open is None
    assert run.backend.embedding_config == existing
    output = capsys.readouterr().out
    assert "seeded account: HTTP 402" in output
    assert "voyage backup: HTTP " in output


def test_without_a_seeded_account_the_test_account_is_used_and_nothing_is_left_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _upstream(_alive) as upstream:
        run = _run(monkeypatch, _secrets(upstream))

    assert run.config_while_open == _account_at(upstream.base)
    assert run.backend.retrieval == {}


def test_a_test_account_switched_to_a_provider_model_id_reaches_the_provider_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``.env.test`` comment says to put ``voyage/voyage-4-lite`` in ``EMBEDDING_MODEL`` and drop the base URL."""
    with _upstream(_alive) as voyage:
        secrets: dict[str, str | None] = {"EMBEDDING_API_KEY": _VOYAGE_KEY, "EMBEDDING_MODEL": "voyage/voyage-4-lite"}
        run = _run(monkeypatch, secrets, voyage_base=voyage.base)

    assert run.config_while_open == _voyage_account()


def test_without_any_account_the_local_server_is_used_and_nothing_is_left_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(monkeypatch, _secrets())

    assert run.config_while_open["provider"] == "openai_compatible"
    assert run.config_while_open["apiKey"] == "test-key"
    assert run.reason_while_open is None
    assert run.backend.retrieval == {}
