# otlp/

## Overview
OTLP export plumbing shared by traces and metrics: one place decides where telemetry goes (standard `OTEL_EXPORTER_OTLP_*` semantics), one factory builds the official exporters, one guard sanitizes what leaves, and one posture document reports what is actually happening. `config.py`, `posture.py` and `stats.py` are importable without the OpenTelemetry SDK; the SDK-bound modules are imported only when a pipeline is built.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | SDK-free facade: configuration helpers and posture writers. | ✅ |
| config.py | Core | Target resolution per signal (per-signal endpoint verbatim, general endpoint + signal path for HTTP, protocol precedence: argument, signal, general, the endpoint's own hint (`:4317` or `grpc://` means gRPC), HTTP; `OTEL_<SIGNAL>_EXPORTER=none`), header parsing, credential-safe endpoint display, kill switch, local-trace-only gate that parses hosts. | ✅ |
| exporters.py | Core | Official OTLP exporter factory (HTTP/protobuf and gRPC, spans and metrics). An unsatisfiable request raises `OtlpUnavailableError`; it never swaps protocol or falls back to stdout, and the error text is scrubbed of the target's header values and URL credentials before it reaches the log, the posture or the UI. | ✅ |
| lifecycle.py | Core | `run_bounded`: provider flush/shutdown on a daemon thread with a deadline, so a hung collector cannot block exit. | ✅ |
| posture.py | Core | Measured posture: status, endpoint, protocol, sampler, content capture, metric pipeline, export counters, last success/failure; every field is read from live state. | ✅ |
| privacy.py | Core | `PrivacyGuardExporter`: sanitized copies of finished spans (metadata only by default, content behind the standard switch, system prompt never, credentials redacted, fail-closed). | ✅ |
| resource.py | Core | Shared `Resource` (service, version, environment, VCS) with the standard `OTEL_SERVICE_NAME` / `OTEL_RESOURCE_ATTRIBUTES` winning over defaults. | ✅ |
| stats.py | Core | `ExportStats`: exported / failed / withheld counters written by the guard and read by the posture. | ✅ |
