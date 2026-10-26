"""What the real claude and codex binaries say when their model API refuses a request, and what ``CliRuntime`` makes of it.

A local stub API answers every request with one canned failure, so nothing here needs a login, a network or a model
(and no model is billed). These guard against drift in the failure frames the classifier reads: Claude's
``authentication_failed`` category and HTTP status, Codex's ``turn.failed`` text and the retry notices it prints
before giving up. The CLIs run through the production runtime with the production argv and environment rules.
Run with ``-m integration``; a CLI that is not installed skips its tests.
"""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.auth import cli_launch_args
from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
)

pytestmark = pytest.mark.integration

_CLAUDE = shutil.which("claude")
_CODEX = shutil.which("codex")

needs_claude = pytest.mark.skipif(_CLAUDE is None, reason="claude CLI not installed")
needs_codex = pytest.mark.skipif(_CODEX is None, reason="codex CLI not installed")

_AUTH_BODY = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
_FORBIDDEN_BODY = {"type": "error", "error": {"type": "permission_error", "message": "Request not allowed"}}
_RATE_LIMIT_BODY = {"type": "error", "error": {"type": "rate_limit_error", "message": "rate limit reached"}}
_OPENAI_ERROR = {"error": {"message": "stub failure", "type": "server_error", "code": None}}

ServeFailure = Callable[[int, dict[str, object]], str]


@pytest.fixture
def serve_failure() -> Iterator[ServeFailure]:
    """Start a local API answering every request with ``status`` and ``body``; yields the function that starts one."""
    servers: list[ThreadingHTTPServer] = []

    def serve(status: int, body: dict[str, object]) -> str:
        payload = json.dumps(body).encode()

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                if length:
                    self.rfile.read(length)
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                self._answer()

            def do_POST(self) -> None:
                self._answer()

            def log_message(self, format: str, *args: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield serve
    for server in servers:
        server.shutdown()
        server.server_close()


def _claude(tmp_path: Path, base_url: str, *, api_key: str | None = "sk-ant-api03-dummy") -> CliRuntime:
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "ANTHROPIC_BASE_URL": base_url,
        "CLAUDE_CODE_MAX_RETRIES": "0",
        "API_TIMEOUT_MS": "8000",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    if api_key is not None:
        env["ANTHROPIC_API_KEY"] = api_key
    config = RuntimeConfig(
        backend_type="cli",
        command=str(_CLAUDE),
        args=cli_launch_args("claude"),
        env=env,
        cwd=str(tmp_path),
        permission_mode="safe",
        auth_mode="api_key",
        timeout_seconds=60,
    )
    return CliRuntime("claude", config)


def _codex(tmp_path: Path, base_url: str, *, retries: int = 0) -> CliRuntime:
    """A codex whose only model provider is the stub (set in its own ``config.toml``, as a user would)."""
    home = tmp_path / "home"
    home.mkdir()
    codex_home = home / ".codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        f"""model_provider = "stub"

[model_providers.stub]
name = "stub"
base_url = "{base_url}/v1"
env_key = "STUB_KEY"
wire_api = "responses"
request_max_retries = {retries}
stream_max_retries = {retries}
"""
    )
    config = RuntimeConfig(
        backend_type="cli",
        command=str(_CODEX),
        args=cli_launch_args("codex"),
        env={"HOME": str(home), "CODEX_HOME": str(codex_home), "STUB_KEY": "stub-key"},
        cwd=str(tmp_path),
        permission_mode="safe",
        auth_mode="api_key",
        timeout_seconds=60,
    )
    return CliRuntime("codex", config)


async def _errors_of(runtime: CliRuntime) -> tuple[list[RuntimeEvent], list[AcpError]]:
    events = [event async for event in runtime.run_turn("hi", "s1")]
    errors = [e.data["error"] for e in events if e.type is RuntimeEventType.ERROR]
    assert all(isinstance(error, AcpError) for error in errors)
    return events, errors


@needs_claude
@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (401, _AUTH_BODY, AcpErrorCode.AUTH_FAILED),
        (403, _FORBIDDEN_BODY, AcpErrorCode.AUTH_FAILED),
        (429, _RATE_LIMIT_BODY, AcpErrorCode.RATE_LIMITED),
    ],
    ids=["unauthorized", "forbidden", "rate-limited"],
)
async def test_claude_names_what_its_api_refused(
    serve_failure: ServeFailure, tmp_path: Path, status: int, body: dict[str, object], code: AcpErrorCode
) -> None:
    _, errors = await _errors_of(_claude(tmp_path, serve_failure(status, body)))

    assert [error.code for error in errors] == [code]
    assert errors[0].message.strip()


@needs_claude
async def test_claude_without_any_credentials_is_an_auth_failure(serve_failure: ServeFailure, tmp_path: Path) -> None:
    # No API key and an empty config dir; the base URL points at the stub so a login found elsewhere can only reach it.
    _, errors = await _errors_of(_claude(tmp_path, serve_failure(401, _AUTH_BODY), api_key=None))

    assert [error.code for error in errors] == [AcpErrorCode.AUTH_FAILED]


@needs_codex
async def test_codex_rejected_key_is_an_auth_failure(serve_failure: ServeFailure, tmp_path: Path) -> None:
    _, errors = await _errors_of(_codex(tmp_path, serve_failure(401, _OPENAI_ERROR)))

    assert [error.code for error in errors] == [AcpErrorCode.AUTH_FAILED]
    assert "401" in errors[0].message


@needs_codex
@pytest.mark.parametrize("status", [403, 429], ids=["forbidden", "quota"])
async def test_codex_failures_other_than_a_rejected_key_are_not_auth_failures(
    serve_failure: ServeFailure, tmp_path: Path, status: int
) -> None:
    # A 403 can be a region or plan limit and a 429 a quota: the key itself was fine, so the user must not be told to sign in.
    _, errors = await _errors_of(_codex(tmp_path, serve_failure(status, _OPENAI_ERROR)))

    assert len(errors) == 1
    assert errors[0].code is not AcpErrorCode.AUTH_FAILED
    assert errors[0].message.strip() not in {"", "{}"}


@needs_codex
async def test_codex_retries_are_not_reported_as_failures(serve_failure: ServeFailure, tmp_path: Path) -> None:
    # Codex prints one `error` line per reconnect attempt and then fails the turn once: only the last is a failure.
    _, errors = await _errors_of(_codex(tmp_path, serve_failure(500, _OPENAI_ERROR), retries=2))

    assert len(errors) == 1
    assert not errors[0].message.startswith("Reconnecting")
