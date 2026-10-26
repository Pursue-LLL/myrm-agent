# tracing/

## Overview
Distributed tracing and metrics on OpenTelemetry. Framework code emits the GenAI span tree (`invoke_agent` → `chat` / `execute_tool`) and the standard GenAI client metrics through the OpenTelemetry API only; the business layer decides whether anything is exported by calling `setup_tracing()` / `setup_metrics()`. Export is standard OTLP (HTTP/protobuf or gRPC) configured by the standard `OTEL_*` environment, and every exported span passes a privacy guard at the exporter boundary.

Detailed design: [TRACE_STORAGE_SYSTEM.md](TRACE_STORAGE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade: setup and consumer APIs for tracing and metrics, bounded dual-channel flush and shutdown, measured posture, and the OTLP environment readings (`configured_endpoints`, `is_local_endpoint`, `redact_endpoint`, `sdk_disabled`) that business-layer diagnostics share with the export path. | ✅ |
| propagation.py | Core | Trace context propagation. Maintains complete trace chains across service calls. | ✅ |
| sanitizer.py | Core | Three-layer progressive privacy sanitizer for OpenTelemetry spans and trace events (credential redaction, bounded truncation); used by the exporter-boundary guard. | ✅ |
| tracer.py | Core | `setup_tracing` (endpoint from the standard OTLP variables, kill switch, SDK-native sampler, privacy-guarded batch export), consumer helpers (`get_tracer`, `trace_async`, `trace_context`), bounded force-flush and shutdown for tracing and metrics. | ✅ |

| Submodule | Description |
|-----------|-------------|
| gen_ai/ | GenAI span tree (`AgentRunSpan`, `ModelCall`, `execute_tool_span`), the naming vocabulary, opt-in content capture and the three standard GenAI client metrics. |
| otlp/ | OTLP plumbing shared by traces and metrics: target resolution, official exporters, privacy guard, resource, bounded lifecycle and the measured posture. |
| metrics/ | Metrics export (OTLP through the shared pipeline, console for development) and the cardinality-guarded `MetricsCollector`. |

## Optional install

- **`[observability]` extra**: `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-exporter-otlp-proto-http`, `openinference-instrumentation-langchain`
- `opentelemetry-api` is a core dependency; the SDK and exporters are optional, and a bare install keeps importing and runs on OpenTelemetry's NoOp providers
- `opentelemetry-instrumentation` is installed transitively via `openinference-instrumentation-langchain`
