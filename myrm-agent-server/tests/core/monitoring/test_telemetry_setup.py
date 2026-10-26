"""Server startup wiring for OpenTelemetry export, run in a fresh interpreter against a real OTLP receiver.

[INPUT]
- app.core.monitoring::_setup_telemetry (POS: the startup hook under test)
- opentelemetry.proto (POS: decoder for what a collector would actually receive)

[OUTPUT]
- Tests proving that standard ``OTEL_*`` variables alone enable export of traces and of the
  harness's production metrics, name the service, and that nothing is exported (or printed) when
  they are absent or the SDK is switched off.

[POS]
Each scenario runs ``_setup_telemetry`` in a child process because OpenTelemetry installs its
providers once per process; a fresh interpreter exercises the same path a real server start does,
without touching this test process's global state.
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import threading
import zlib
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Self

import pytest
from myrm_agent_harness import __version__ as engine_version
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

pytestmark = pytest.mark.integration

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_POSTURE_PREFIX = "POSTURE="

_STARTUP_PROBE = f"""
import json

from opentelemetry import trace

from myrm_agent_harness.infra.tracing import (
    force_flush_metrics,
    force_flush_tracing,
    get_telemetry_posture,
    shutdown_observability,
)
from myrm_agent_harness.toolkits.memory.metrics import get_search_metrics

from app.core.monitoring import _setup_telemetry

# A production instrument is created before any provider exists (as at server import time) and recorded after startup.
search_metrics = get_search_metrics()
_setup_telemetry()
with trace.get_tracer("startup-probe").start_as_current_span("startup.probe"):
    pass
with search_metrics.track_search() as search:
    search.record([])
force_flush_tracing(5000)
force_flush_metrics(5000)
posture = get_telemetry_posture()
shutdown_observability(timeout_ms=5000)
print("{_POSTURE_PREFIX}" + json.dumps(posture))
"""


@dataclass
class _Received:
    paths: list[str] = field(default_factory=list)
    traces: list[ExportTraceServiceRequest] = field(default_factory=list)
    metrics: list[ExportMetricsServiceRequest] = field(default_factory=list)


class _OtlpReceiver:
    """Minimal OTLP/HTTP collector: decodes trace exports and acknowledges everything else."""

    def __init__(self) -> None:
        received = self.received = _Received()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                encoding = self.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    body = gzip.decompress(body)
                elif encoding == "deflate":
                    body = zlib.decompress(body)
                received.paths.append(self.path)
                if self.path.endswith("/v1/traces"):
                    trace_request = ExportTraceServiceRequest()
                    trace_request.ParseFromString(body)
                    received.traces.append(trace_request)
                    payload = ExportTraceServiceResponse().SerializeToString()
                else:
                    metrics_request = ExportMetricsServiceRequest()
                    metrics_request.ParseFromString(body)
                    received.metrics.append(metrics_request)
                    payload = ExportMetricsServiceResponse().SerializeToString()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def resource_attributes(self) -> dict[str, str]:
        resource = self.received.traces[0].resource_spans[0].resource
        return {item.key: item.value.string_value for item in resource.attributes}

    def metric_names(self) -> set[str]:
        return {
            metric.name
            for request in self.received.metrics
            for resource_metrics in request.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        }

    def span_names(self) -> list[str]:
        return [
            span.name
            for request in self.received.traces
            for resource_spans in request.resource_spans
            for scope_spans in resource_spans.scope_spans
            for span in scope_spans.spans
        ]


def _start_server_telemetry(**environment: str) -> tuple[dict[str, object], str]:
    """Run the startup hook in a fresh interpreter; return the measured posture and its stdout."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("OTEL_")}
    env.update({"DEPLOY_MODE": "local", "OTEL_EXPORTER_OTLP_ENDPOINT": "", **environment})
    completed = subprocess.run(
        [sys.executable, "-c", _STARTUP_PROBE],
        cwd=_SERVER_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    line = next(line for line in completed.stdout.splitlines() if line.startswith(_POSTURE_PREFIX))
    return json.loads(line.removeprefix(_POSTURE_PREFIX)), completed.stdout


def test_standard_endpoint_alone_exports_traces_with_the_server_identity() -> None:
    with _OtlpReceiver() as receiver:
        posture, _ = _start_server_telemetry(OTEL_EXPORTER_OTLP_ENDPOINT=receiver.endpoint)

    assert "/v1/traces" in receiver.received.paths
    assert receiver.span_names() == ["startup.probe"]
    attributes = receiver.resource_attributes()
    assert attributes["service.name"] == "myrm-agent-server"
    assert attributes["service.version"] == engine_version
    assert attributes["deployment.environment.name"] == "local"

    assert posture["status"] == "active"
    assert posture["exporter_type"] == "otlp_http"
    assert posture["exported_spans"] == 1
    assert posture["failed_batches"] == 0
    assert posture["metrics_exporting"] is True
    assert posture["content_capture"] is False


def test_production_instruments_created_before_startup_are_exported() -> None:
    with _OtlpReceiver() as receiver:
        _start_server_telemetry(OTEL_EXPORTER_OTLP_ENDPOINT=receiver.endpoint)

    assert "/v1/metrics" in receiver.received.paths
    assert {"memory_search_total", "memory_search_zero_result_total", "memory_search_latency_ms"} <= receiver.metric_names()


def test_operator_resource_attributes_win_over_server_defaults() -> None:
    with _OtlpReceiver() as receiver:
        _start_server_telemetry(
            OTEL_EXPORTER_OTLP_ENDPOINT=receiver.endpoint,
            OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=staging,service.instance.id=sandbox-7",
        )

    attributes = receiver.resource_attributes()
    assert attributes["deployment.environment.name"] == "staging"
    assert attributes["service.instance.id"] == "sandbox-7"
    assert attributes["service.name"] == "myrm-agent-server"


def test_without_an_endpoint_nothing_is_exported_or_printed() -> None:
    posture, stdout = _start_server_telemetry()

    assert posture["status"] == "noop"
    assert posture["initialized"] is False
    assert posture["exported_spans"] == 0
    assert posture["metrics_exporting"] is False
    assert "startup.probe" not in stdout


def test_the_standard_kill_switch_disables_export_even_with_an_endpoint() -> None:
    with _OtlpReceiver() as receiver:
        posture, _ = _start_server_telemetry(
            OTEL_EXPORTER_OTLP_ENDPOINT=receiver.endpoint,
            OTEL_SDK_DISABLED="true",
        )

    assert receiver.received.paths == []
    assert posture["status"] == "disabled"
    assert posture["exported_spans"] == 0
