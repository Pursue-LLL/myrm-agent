"""The id a user is shown is the trace id the backend stores: header, error body and exported spans agree.

[INPUT]
- app.core.monitoring::_setup_telemetry (POS: installs the pipeline with the context trace id generator)
- app.middleware.observability::TracingMiddleware (POS: binds the request's trace id)
- tests.support.otlp_receiver::OtlpReceiver (POS: decoder for what a collector would actually receive)

[OUTPUT]
- Tests proving that a span started while a request is served is exported under that request's trace id,
  for a plain response, a streamed response (how chat answers), a server fault and an unhandled exception,
  with a generated and with an inbound id.

[POS]
Runs in a fresh interpreter because OpenTelemetry installs its providers once per process. The application is
built with ``FASTAPI_TELEMETRY`` as ``app.main`` is: FastAPI's own request span would be created outside
``TracingMiddleware`` with a random trace id that every span below it inherits. The agent's root span is started
inside ``asyncio.create_task`` as the orchestrator does, which is what the context variable has to survive.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.otlp_receiver import OtlpReceiver

pytestmark = pytest.mark.integration

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_RESULT_PREFIX = "RESULT="
_INBOUND_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"

_PROBE = f"""
import asyncio
import json

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from myrm_agent_harness.infra.tracing import force_flush_tracing, shutdown_observability

from app.core.monitoring import FASTAPI_TELEMETRY, _setup_telemetry
from app.core.utils.errors import MyrmError, register_exception_handlers
from app.middleware.observability import TracingMiddleware
from app.schemas.responses import BusinessCode
from app.server.exceptions import general_exception_handler, not_found_handler

_setup_telemetry()
app = FastAPI(telemetry=FASTAPI_TELEMETRY)
register_exception_handlers(app)
app.add_exception_handler(404, not_found_handler)
app.add_exception_handler(Exception, general_exception_handler)


async def run_agent_turn() -> None:
    with trace.get_tracer("probe").start_as_current_span("agent.turn"):
        pass


@app.get("/chat")
async def chat() -> str:
    await asyncio.create_task(run_agent_turn())
    return "ok"


@app.get("/stream")
async def stream() -> StreamingResponse:
    async def events():
        await asyncio.create_task(run_agent_turn())
        yield b"data: hello\\n\\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/fault")
async def fault() -> None:
    await asyncio.create_task(run_agent_turn())
    raise MyrmError(BusinessCode.DB_QUERY_ERROR, "failed")


@app.get("/crash")
async def crash() -> None:
    await asyncio.create_task(run_agent_turn())
    raise RuntimeError("boom")


app.add_middleware(TracingMiddleware)


async def drive() -> dict[str, dict[str, str | None]]:
    results: dict[str, dict[str, str | None]] = {{}}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://probe") as client:
        for name, path, headers in (
            ("chat", "/chat", {{}}),
            ("stream", "/stream", {{}}),
            ("fault", "/fault", {{}}),
            ("crash", "/crash", {{}}),
            ("inbound", "/chat", {{"X-Trace-Id": "{_INBOUND_TRACE_ID}"}}),
        ):
            response = await client.get(path, headers=headers)
            error = response.json().get("error") if name in ("fault", "crash") else None
            results[name] = {{
                "header": response.headers.get("x-trace-id"),
                "body": error["trace_id"] if error else None,
            }}
    return results


outcome = asyncio.run(drive())
force_flush_tracing(5000)
shutdown_observability(timeout_ms=5000)
print("{_RESULT_PREFIX}" + json.dumps(outcome))
"""


def _drive_requests() -> tuple[dict[str, dict[str, str | None]], list[str]]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OTEL_", "FASTAPI_OTEL_"))}
    with OtlpReceiver() as receiver:
        env.update({"DEPLOY_MODE": "local", "OTEL_EXPORTER_OTLP_ENDPOINT": receiver.endpoint})
        completed = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=_SERVER_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    assert completed.returncode == 0, completed.stderr[-3000:]
    line = next(line for line in completed.stdout.splitlines() if line.startswith(_RESULT_PREFIX))
    exported = [span.trace_id for span in receiver.spans() if span.name == "agent.turn"]
    return json.loads(line[len(_RESULT_PREFIX) :]), exported


def test_spans_are_exported_under_the_trace_id_the_user_is_shown() -> None:
    outcome, exported = _drive_requests()

    shown = [outcome[name]["header"] for name in ("chat", "stream", "fault", "crash", "inbound")]
    assert all(shown), outcome
    assert sorted(exported) == sorted(str(trace_id) for trace_id in shown)
    assert outcome["inbound"]["header"] == _INBOUND_TRACE_ID


def test_error_bodies_carry_the_same_id_as_the_header() -> None:
    outcome, _ = _drive_requests()

    for name in ("fault", "crash"):
        assert outcome[name]["body"] == outcome[name]["header"], outcome
