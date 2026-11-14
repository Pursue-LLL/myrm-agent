"""LangSmith's upload is a second trace export path; the zero-egress policy has to close it too."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator

import pytest
from langsmith.utils import get_env_var, tracing_is_enabled

from myrm_agent_harness.infra.tracing import langsmith_tracing_requested, setup_tracing
from myrm_agent_harness.infra.tracing.langsmith_gate import LANGSMITH_TRACING_SWITCHES, block_langsmith_tracing


@pytest.fixture(autouse=True)
def _clean_langsmith_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """LangSmith caches what it read from the environment: start and end every test with an empty cache."""
    for name in LANGSMITH_TRACING_SWITCHES:
        monkeypatch.delenv(name, raising=False)
    get_env_var.cache_clear()
    yield
    get_env_var.cache_clear()


@pytest.mark.parametrize("name", LANGSMITH_TRACING_SWITCHES)
def test_every_switch_langsmith_reads_counts_as_requested(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not langsmith_tracing_requested()
    monkeypatch.setenv(name, "true")
    assert langsmith_tracing_requested()
    monkeypatch.setenv(name, "false")
    assert not langsmith_tracing_requested()


def test_blocking_turns_every_switch_off_even_after_langsmith_cached_the_old_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    assert tracing_is_enabled() is True  # LangSmith has now cached the switch

    assert block_langsmith_tracing() is True

    assert tracing_is_enabled() is False
    assert not langsmith_tracing_requested()
    assert {os.environ[name] for name in LANGSMITH_TRACING_SWITCHES} == {"false"}


def test_blocking_leaves_an_environment_without_the_switch_untouched() -> None:
    assert block_langsmith_tracing() is False
    assert not any(name in os.environ for name in LANGSMITH_TRACING_SWITCHES)


@pytest.mark.parametrize("via", ["environment", "argument"])
def test_setup_tracing_blocks_langsmith_under_the_zero_egress_policy(via: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    if via == "environment":
        monkeypatch.setenv("MYRM_LOCAL_TRACE_ONLY", "1")

    setup_tracing(local_trace_only=via == "argument")

    assert not langsmith_tracing_requested()


def test_setup_tracing_blocks_langsmith_before_a_refused_remote_endpoint_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("MYRM_LOCAL_TRACE_ONLY", "1")

    with pytest.raises(PermissionError):
        setup_tracing(otlp_endpoint="https://collector.example:4318")

    assert not langsmith_tracing_requested()


def test_setup_tracing_leaves_langsmith_alone_without_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    setup_tracing()

    assert langsmith_tracing_requested()


# A real LangChain run in a fresh interpreter (the SDK keeps process-wide state), with a local HTTP server
# standing in for LangSmith. It reports every request the run sent there.
_RUN_AGAINST_FAKE_LANGSMITH = textwrap.dedent(
    """
    import http.server, json, os, threading, time

    received: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("content-length", "0") or 0)
            body = self.rfile.read(length) if length else b""
            received.append(self.path + (" +prompt" if b"SECRET-PROMPT" in body else ""))
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = do_POST = do_PUT = do_PATCH = _answer

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ.update(
        LANGSMITH_TRACING="true",
        LANGSMITH_API_KEY="lsv2_test_key",
        LANGSMITH_ENDPOINT=f"http://127.0.0.1:{server.server_address[1]}",
    )

    from langchain_core.runnables import RunnableLambda
    from langchain_core.tracers.langchain import wait_for_all_tracers

    from myrm_agent_harness.infra.tracing import setup_tracing

    setup_tracing()
    RunnableLambda(lambda text: f"SECRET-PROMPT-{text}").invoke("hello")
    wait_for_all_tracers()
    time.sleep(1.0)
    print(json.dumps(received))
    """
)


def _requests_langsmith_received(*, zero_egress_policy: bool) -> list[str]:
    env = {key: value for key, value in os.environ.items() if key not in LANGSMITH_TRACING_SWITCHES}
    env.pop("MYRM_LOCAL_TRACE_ONLY", None)
    if zero_egress_policy:
        env["MYRM_LOCAL_TRACE_ONLY"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", _RUN_AGAINST_FAKE_LANGSMITH],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    received: list[str] = json.loads(result.stdout.strip().splitlines()[-1])
    return received


def test_a_langchain_run_uploads_without_the_policy_and_sends_nothing_under_it() -> None:
    without_policy = _requests_langsmith_received(zero_egress_policy=False)
    assert any(request.startswith("/runs") and request.endswith("+prompt") for request in without_policy), (
        without_policy
    )

    assert _requests_langsmith_received(zero_egress_policy=True) == []
