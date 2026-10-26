"""Loopback OTLP/HTTP collector that decodes what a telemetry exporter really sent.

[INPUT]
- opentelemetry.proto (POS: decoder for what a collector would actually receive)

[OUTPUT]
- OtlpReceiver: context manager serving ``/v1/traces``, ``/v1/metrics`` and ``/v1/logs`` on an ephemeral port
- ReceivedSpan: one exported span with its ids, kind and attributes

[POS]
Test-only. Child-process telemetry probes export to it, so assertions are made on the bytes a real
backend would receive instead of on mocks of the exporter.
"""

from __future__ import annotations

import gzip
import threading
import zlib
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Self

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue

type Attribute = str | int | float | bool


def _attribute(value: AnyValue) -> Attribute:
    kind = value.WhichOneof("value")
    match kind:
        case "string_value":
            return value.string_value
        case "int_value":
            return value.int_value
        case "double_value":
            return value.double_value
        case "bool_value":
            return value.bool_value
        case _:
            return ""


def _attributes(items: list[KeyValue]) -> dict[str, Attribute]:
    return {item.key: _attribute(item.value) for item in items}


@dataclass(frozen=True, slots=True)
class ReceivedSpan:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str
    kind: int
    attributes: dict[str, Attribute]


@dataclass
class _Received:
    paths: list[str] = field(default_factory=list)
    traces: list[ExportTraceServiceRequest] = field(default_factory=list)
    metrics: list[ExportMetricsServiceRequest] = field(default_factory=list)
    logs: list[ExportLogsServiceRequest] = field(default_factory=list)


class OtlpReceiver:
    """Minimal OTLP/HTTP collector: decodes trace and metric exports and acknowledges them."""

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
                elif self.path.endswith("/v1/logs"):
                    logs_request = ExportLogsServiceRequest()
                    logs_request.ParseFromString(body)
                    received.logs.append(logs_request)
                    payload = ExportLogsServiceResponse().SerializeToString()
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

    def spans(self) -> list[ReceivedSpan]:
        return [
            ReceivedSpan(
                name=span.name,
                trace_id=span.trace_id.hex(),
                span_id=span.span_id.hex(),
                parent_span_id=span.parent_span_id.hex(),
                kind=span.kind,
                attributes=_attributes(list(span.attributes)),
            )
            for request in self.received.traces
            for resource_spans in request.resource_spans
            for scope_spans in resource_spans.scope_spans
            for span in scope_spans.spans
        ]

    def span_names(self) -> list[str]:
        return [span.name for span in self.spans()]

    def metric_names(self) -> set[str]:
        return {
            metric.name
            for request in self.received.metrics
            for resource_metrics in request.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        }

    def metric_export_count(self, metric_name: str) -> int:
        """How many export requests carried ``metric_name``: one per reader that pushed it."""
        return sum(
            any(
                metric.name == metric_name
                for resource_metrics in request.resource_metrics
                for scope_metrics in resource_metrics.scope_metrics
                for metric in scope_metrics.metrics
            )
            for request in self.received.metrics
        )

    def log_attribute_values(self, key: str) -> list[Attribute]:
        """The value of attribute ``key`` on every exported log record that carries it."""
        values: list[Attribute] = []
        for request in self.received.logs:
            for resource_logs in request.resource_logs:
                for scope_logs in resource_logs.scope_logs:
                    for record in scope_logs.log_records:
                        attributes = _attributes(list(record.attributes))
                        if key in attributes:
                            values.append(attributes[key])
        return values

    def metric_attribute_values(self, metric_name: str, key: str) -> set[Attribute]:
        """Every value that data points of ``metric_name`` carry under the attribute ``key``."""
        values: set[Attribute] = set()
        for request in self.received.metrics:
            for resource_metrics in request.resource_metrics:
                for scope_metrics in resource_metrics.scope_metrics:
                    for metric in scope_metrics.metrics:
                        if metric.name != metric_name:
                            continue
                        data = getattr(metric, metric.WhichOneof("data") or "gauge")
                        for point in data.data_points:
                            attributes = _attributes(list(point.attributes))
                            if key in attributes:
                                values.add(attributes[key])
        return values
