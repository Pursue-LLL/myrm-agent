"""FastAPI's own telemetry adds neither request spans nor a second export path beside the harness pipeline.

[INPUT]
- app.main::app (POS: the real application, built with FastAPI(telemetry=FASTAPI_TELEMETRY))
- app.core.monitoring::FASTAPI_TELEMETRY (POS: the policy under test)
- tests.support.otlp_receiver::OtlpReceiver (POS: decoder for what a collector would actually receive)

[OUTPUT]
- Tests proving that health probes against the real application create no trace while their request
  metrics are exported, and that FastAPI's environment auto-configuration (``FASTAPI_OTEL_AUTO_CONFIGURE``)
  cannot duplicate spans or metrics or ship exception messages and stack traces to the backend.

[POS]
Each scenario runs in a fresh interpreter because OpenTelemetry installs its providers once per
process. A control application without the policy runs next to the real one, so that every claim of
"nothing extra is exported" is measured against what FastAPI does by default instead of assumed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.otlp_receiver import OtlpReceiver

pytestmark = pytest.mark.integration

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_REQUEST_DURATION = "http.server.request.duration"
_PRIVATE_PROMPT = "a prompt that must stay on this machine"
_PRIVATE_FAILURE = "a failure message that must stay on this machine"

_REAL_APP_PROBE = """
import asyncio

import httpx
from fastapi import FastAPI
from opentelemetry import trace

from myrm_agent_harness.infra.tracing import force_flush_metrics, force_flush_tracing, shutdown_observability

from app.core.monitoring import _setup_telemetry
from app.main import app

control = FastAPI()


@control.get("/control")
async def _control() -> str:
    return "ok"


_setup_telemetry()


async def drive() -> None:
    for target, path in ((app, "/health"), (control, "/control")):
        transport = httpx.ASGITransport(app=target)
        async with httpx.AsyncClient(transport=transport, base_url="http://probe") as client:
            for _ in range(3):
                assert (await client.get(path)).status_code == 200


asyncio.run(drive())
with trace.get_tracer("probe").start_as_current_span("agent.step"):
    pass
force_flush_tracing(5000)
force_flush_metrics(5000)
shutdown_observability(timeout_ms=5000)
"""

_AUTO_CONFIGURE_PROBE = f"""
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace

from myrm_agent_harness.infra.tracing import force_flush_metrics, force_flush_tracing, shutdown_observability

from app.core.monitoring import FASTAPI_TELEMETRY, _setup_telemetry

_setup_telemetry()
app = FastAPI(telemetry=FASTAPI_TELEMETRY) if sys.argv[1] == "policy" else FastAPI()


@app.get("/ok")
async def ok() -> str:
    return "ok"


@app.get("/fail")
async def fail() -> str:
    raise RuntimeError({_PRIVATE_FAILURE!r})


with TestClient(app, raise_server_exceptions=False) as client:  # lifespan startup is where FastAPI adds exporters
    client.get("/ok")
    client.get("/fail")
    with trace.get_tracer("probe").start_as_current_span("agent.step") as span:
        span.set_attribute("input.value", {_PRIVATE_PROMPT!r})
    force_flush_tracing(5000)
    force_flush_metrics(5000)
shutdown_observability(timeout_ms=5000)
"""


def _run_probe(probe: str, *args: str, receiver: OtlpReceiver, **environment: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OTEL_", "FASTAPI_OTEL_"))}
    env.update({"DEPLOY_MODE": "local", "OTEL_EXPORTER_OTLP_ENDPOINT": receiver.endpoint, **environment})
    completed = subprocess.run(
        [sys.executable, "-c", probe, *args],
        cwd=_SERVER_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]


def _deliver(variant: str, *, auto_configure: bool) -> OtlpReceiver:
    """Run the auto-configure probe against a fresh collector, with FastAPI's env auto-configuration on or off."""
    environment = {"FASTAPI_OTEL_AUTO_CONFIGURE": "true"} if auto_configure else {}
    with OtlpReceiver() as receiver:
        _run_probe(_AUTO_CONFIGURE_PROBE, variant, receiver=receiver, **environment)
    return receiver


def test_health_probes_create_no_trace_but_their_request_metrics_are_exported() -> None:
    with OtlpReceiver() as receiver:
        _run_probe(_REAL_APP_PROBE, receiver=receiver)

    spans = receiver.spans()
    control_spans = [span for span in spans if span.attributes.get("code.function.name") == "__main__._control"]
    control_requests = [span for span in spans if span.attributes.get("http.route") == "/control"]
    assert control_spans and control_requests, "FastAPI without the policy must emit spans, or this test proves nothing"
    assert [span.name for span in spans if span not in control_spans + control_requests] == ["agent.step"]
    assert _REQUEST_DURATION in receiver.metric_names()
    assert "/health" in receiver.metric_attribute_values(_REQUEST_DURATION, "http.route")


def test_environment_auto_configuration_adds_no_second_export_path() -> None:
    baseline = _deliver("policy", auto_configure=False)
    configured = _deliver("policy", auto_configure=True)

    spans = [span for span in configured.spans() if span.name == "agent.step"]
    assert len(spans) == 1
    assert not any(span.attributes.get("input.value") == _PRIVATE_PROMPT for span in spans)
    assert configured.metric_export_count(_REQUEST_DURATION) == baseline.metric_export_count(_REQUEST_DURATION) > 0
    assert "/v1/logs" not in configured.received.paths
    assert configured.log_attribute_values("exception.message") == []


def test_fastapi_default_auto_configuration_duplicates_signals_and_ships_exceptions() -> None:
    """The hazard the policy removes: if FastAPI stops doing this, re-evaluate whether the policy is still needed."""
    baseline = _deliver("fastapi-default", auto_configure=False)
    configured = _deliver("fastapi-default", auto_configure=True)

    spans = [span for span in configured.spans() if span.name == "agent.step"]
    assert len(spans) == 2
    assert any(span.attributes.get("input.value") == _PRIVATE_PROMPT for span in spans)
    assert configured.metric_export_count(_REQUEST_DURATION) > baseline.metric_export_count(_REQUEST_DURATION)
    assert configured.log_attribute_values("exception.message") == [_PRIVATE_FAILURE]
