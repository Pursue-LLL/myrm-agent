"""In-process OTLP receivers (HTTP/protobuf and gRPC) that decode what an exporter really sent.

The tests in this package assert on the bytes that reach a collector, not on mocks of the
exporter: an endpoint that is wrong, a header that is dropped or a content attribute that leaks
only shows up on the wire.
"""

from __future__ import annotations

import gzip
import threading
import time
import zlib
from collections.abc import Callable
from concurrent import futures
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue

if TYPE_CHECKING:
    import grpc
    from google.protobuf.message import Message

type Scalar = str | int | float | bool | bytes | list["Scalar"] | dict[str, "Scalar"] | None


def any_value(value: AnyValue) -> Scalar:
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    raw = getattr(value, kind)
    if kind == "array_value":
        return [any_value(item) for item in raw.values]
    if kind == "kvlist_value":
        return {item.key: any_value(item.value) for item in raw.values}
    scalar: Scalar = raw
    return scalar


def attributes_of(items: list[KeyValue]) -> dict[str, Scalar]:
    return {item.key: any_value(item.value) for item in items}


@dataclass(frozen=True, slots=True)
class ReceivedEvent:
    name: str
    attributes: dict[str, Scalar]


@dataclass(frozen=True, slots=True)
class ReceivedSpan:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str
    kind: int
    attributes: dict[str, Scalar]
    events: list[ReceivedEvent]
    status_code: int
    status_message: str
    resource: dict[str, Scalar]
    scope: str
    link_attributes: list[dict[str, Scalar]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReceivedMetric:
    name: str
    unit: str
    kind: str
    resource: dict[str, Scalar]
    points: list[dict[str, Scalar]]


@dataclass(frozen=True, slots=True)
class ReceivedRequest:
    path: str
    headers: dict[str, str]
    body: Message


def _spans(request: trace_service_pb2.ExportTraceServiceRequest) -> list[ReceivedSpan]:
    received: list[ReceivedSpan] = []
    for resource_spans in request.resource_spans:
        resource = attributes_of(list(resource_spans.resource.attributes))
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                received.append(
                    ReceivedSpan(
                        name=span.name,
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=span.parent_span_id.hex(),
                        kind=span.kind,
                        attributes=attributes_of(list(span.attributes)),
                        events=[ReceivedEvent(e.name, attributes_of(list(e.attributes))) for e in span.events],
                        status_code=span.status.code,
                        status_message=span.status.message,
                        resource=resource,
                        scope=scope_spans.scope.name,
                        link_attributes=[attributes_of(list(link.attributes)) for link in span.links],
                    )
                )
    return received


def _metrics(request: metrics_service_pb2.ExportMetricsServiceRequest) -> list[ReceivedMetric]:
    received: list[ReceivedMetric] = []
    for resource_metrics in request.resource_metrics:
        resource = attributes_of(list(resource_metrics.resource.attributes))
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                kind = metric.WhichOneof("data") or "unknown"
                data_points = list(getattr(metric, kind).data_points) if kind != "unknown" else []
                points: list[dict[str, Scalar]] = []
                for point in data_points:
                    entry: dict[str, Scalar] = dict(attributes_of(list(point.attributes)))
                    if hasattr(point, "count"):
                        entry["__count"] = point.count
                        entry["__sum"] = point.sum
                    elif hasattr(point, "as_int"):
                        entry["__value"] = point.as_int or point.as_double
                    points.append(entry)
                received.append(ReceivedMetric(metric.name, metric.unit, kind, resource, points))
    return received


class _Collected:
    """Requests received by a receiver, decoded on demand."""

    def __init__(self) -> None:
        self.requests: list[ReceivedRequest] = []
        self._lock = threading.Lock()

    def add(self, request: ReceivedRequest) -> None:
        with self._lock:
            self.requests.append(request)

    def spans(self) -> list[ReceivedSpan]:
        with self._lock:
            items = list(self.requests)
        return [
            span
            for item in items
            if isinstance(item.body, trace_service_pb2.ExportTraceServiceRequest)
            for span in _spans(item.body)
        ]

    def metrics(self) -> list[ReceivedMetric]:
        with self._lock:
            items = list(self.requests)
        return [
            metric
            for item in items
            if isinstance(item.body, metrics_service_pb2.ExportMetricsServiceRequest)
            for metric in _metrics(item.body)
        ]

    def paths(self) -> list[str]:
        with self._lock:
            return [item.path for item in self.requests]

    def wait_for(self, predicate: Callable[[], bool], timeout_s: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()


class OtlpHttpReceiver(_Collected):
    """OTLP/HTTP protobuf collector on an ephemeral loopback port."""

    def __init__(self, *, status: int = 200) -> None:
        super().__init__()
        self.status = status
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                encoding = self.headers.get("Content-Encoding", "")
                if encoding == "gzip":
                    raw = gzip.decompress(raw)
                elif encoding == "deflate":
                    raw = zlib.decompress(raw)
                body: Message
                response: Message
                if self.path.endswith("/v1/traces"):
                    body = trace_service_pb2.ExportTraceServiceRequest()
                    response = trace_service_pb2.ExportTraceServiceResponse()
                elif self.path.endswith("/v1/metrics"):
                    body = metrics_service_pb2.ExportMetricsServiceRequest()
                    response = metrics_service_pb2.ExportMetricsServiceResponse()
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                body.ParseFromString(raw)
                receiver.add(ReceivedRequest(self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                payload = response.SerializeToString()
                self.send_response(receiver.status)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="otlp-http-receiver", daemon=True)

    @property
    def endpoint(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class OtlpGrpcReceiver(_Collected):
    """OTLP/gRPC collector on an ephemeral loopback port."""

    def __init__(self) -> None:
        super().__init__()
        receiver = self

        class Traces(trace_service_pb2_grpc.TraceServiceServicer):
            def Export(  # noqa: N802
                self, request: trace_service_pb2.ExportTraceServiceRequest, context: grpc.ServicerContext
            ) -> trace_service_pb2.ExportTraceServiceResponse:
                receiver.add(ReceivedRequest("traces", dict(context.invocation_metadata()), request))
                return trace_service_pb2.ExportTraceServiceResponse()

        class Metrics(metrics_service_pb2_grpc.MetricsServiceServicer):
            def Export(  # noqa: N802
                self, request: metrics_service_pb2.ExportMetricsServiceRequest, context: grpc.ServicerContext
            ) -> metrics_service_pb2.ExportMetricsServiceResponse:
                receiver.add(ReceivedRequest("metrics", dict(context.invocation_metadata()), request))
                return metrics_service_pb2.ExportMetricsServiceResponse()

        import grpc

        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(Traces(), self._server)
        metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(Metrics(), self._server)
        self._port = self._server.add_insecure_port("127.0.0.1:0")

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self) -> None:
        self._server.start()

    def stop(self) -> None:
        self._server.stop(grace=1).wait(5)
