# Trace Storage Integration Guide

> Export agent traces and metrics to Jaeger, Grafana Tempo, Langfuse, Phoenix, Datadog or any other OTLP-compatible backend, configured entirely through the standard OpenTelemetry environment.

## Overview

`myrm-agent-harness` emits OpenTelemetry telemetry through the OpenTelemetry **API** only:

- **GenAI span tree** per agent run: `invoke_agent {agent}` → `chat {model}` / `execute_tool {tool}`; sub-agents appear as subtrees under the tool call that started them.
- **Standard GenAI client metrics** per model call: `gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, `gen_ai.client.operation.time_to_first_chunk`.
- **Consumer helpers** for framework code: `get_tracer()`, `trace_async()`, `trace_context()`.
- **Setup helpers** for the business layer: `setup_tracing()`, `setup_metrics()`. The framework never calls them itself.

Without a setup call (or without an endpoint) OpenTelemetry keeps its NoOp providers: nothing is recorded and nothing leaves the process (the instrumentation itself measured 6.9 µs per model call at the median with the NoOp providers and 55 µs with an SDK provider exporting to an in-memory exporter, on macOS with Python 3.13, far below any model latency). What is exported is decided in one place, the exporter-boundary privacy guard (see [Privacy](#privacy)).

---

## Quick Start: Jaeger over OTLP/HTTP

### 1. Install

```bash
uv sync --extra observability   # SDK + OTLP/HTTP and OTLP/gRPC exporters
```

### 2. Start a backend

```bash
docker run --rm -d --name jaeger \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

UI: `http://localhost:16686`

### 3. Point the process at it

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_SERVICE_NAME=my-agent
```

### 4. Initialize in the business layer

```python
from myrm_agent_harness.infra.tracing import setup_tracing
from myrm_agent_harness.infra.tracing.metrics import setup_metrics

setup_tracing(service_name="my-agent")
setup_metrics(service_name="my-agent")
```

Both calls read the same endpoint, protocol, headers and resource. Export is on exactly when an endpoint is configured.

### 5. Verify

```python
from myrm_agent_harness.infra.tracing import get_telemetry_posture

print(get_telemetry_posture())  # status, endpoint, protocol, sampler, exported/failed counters
```

`status` is `ready` once the pipeline is built and until the first batch has been delivered or refused (nothing proves the destination works yet), `active` while the latest batch was accepted, `failing` after the last export failed, `degraded` when the requested protocol cannot be served, `disabled` under the kill switch, `noop` without an endpoint. Every field is measured from live state, and credentials in the endpoint are redacted.

---

## Configuration

All settings are the standard OpenTelemetry variables. Arguments of `setup_tracing()` / `setup_metrics()` win over the environment.

| Variable | Effect |
|----------|--------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base URL for traces and metrics. HTTP/protobuf appends `/v1/traces` or `/v1/metrics`; gRPC uses it as given. Setting it switches export on. |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` / `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Per-signal URL, used verbatim. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` (and per-signal variants) | `http/protobuf` (default) or `grpc`. When unset, an endpoint on the conventional gRPC port `4317` (or a `grpc://` URL, dialled as plaintext) selects gRPC. |
| `OTEL_EXPORTER_OTLP_HEADERS` | `key=value,key2=value2` (URL-decoded), e.g. `Authorization=Bearer%20<token>`. Never shown in the posture. |
| `OTEL_EXPORTER_OTLP_TIMEOUT`, `..._COMPRESSION`, `..._CERTIFICATE` | Read by the official exporters. |
| `OTEL_TRACES_EXPORTER=none` / `OTEL_METRICS_EXPORTER=none` | Switch one signal off while an endpoint is configured. |
| `OTEL_SDK_DISABLED=true` | Kill switch for tracing and metrics. |
| `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | Win over the defaults the application passes (this is how an operator labels an instance without a code change). |
| `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` | Sampling, handled by the SDK (see [Sampling](#sampling)). |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Opt-in capture of prompt, reply and tool content (see [Privacy](#privacy)). |
| `MYRM_LOCAL_TRACE_ONLY=1` | Zero-egress policy: a remote endpoint is refused. The host is parsed (`localhost.attacker.example` is remote). |
| `OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED=true` | SDK self-monitoring metrics (`otel.sdk.processor.span.queue.size`, `.queue.capacity`, `.processed`, `otel.sdk.span.live`, `otel.sdk.span.started`); needs `setup_metrics()`, read when the tracer provider is created. |

A protocol that cannot be served (the exporter package is missing) leaves that signal **off** and is reported by the posture. The framework never swaps to another protocol or to stdout, because that would silently point telemetry at an endpoint that does not speak it.

### gRPC

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

### Authenticated SaaS backend

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.example.com
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20<token>"
```

---

## Span tree

```
invoke_agent ReactAgent                 gen_ai.operation.name, gen_ai.agent.name, gen_ai.conversation.id, agent.status
├── chat deepseek-chat                  gen_ai.provider.name, gen_ai.request.*, gen_ai.response.*, gen_ai.usage.*
│     (events: attempt_failed {retry.attempt, error.type})
├── execute_tool web_search             gen_ai.tool.name, gen_ai.tool.call.id, gen_ai.tool.type
│   └── invoke_agent ResearchAgent      (sub-agent subtree)
│       └── chat ...
└── chat deepseek-chat
```

- One `chat` span per **logical** model call, streaming or not. Empty-response and parameter-recovery retries are `attempt_failed` events on that span, not sibling spans. An answer replayed from the call memo makes no model call, so it creates no span, no tokens and no metrics.
- Token usage follows the convention: `gen_ai.usage.input_tokens` includes cache read and cache creation tokens, which are reported separately as `gen_ai.usage.cache_read.input_tokens` / `gen_ai.usage.cache_creation.input_tokens`; reasoning tokens as `gen_ai.usage.reasoning.output_tokens`.
- `agent.status` is `completed`, `error` or `cancelled`. A consumer that stops reading early is `cancelled`, not an error.
- Failure is recorded as an error class (`error.type`); error text is not exported.

### Metrics

Recorded once per model call from the call's own measurements, independent of trace sampling:

| Metric | Unit | Dimensions |
|--------|------|------------|
| `gen_ai.client.token.usage` | `{token}` | operation, provider, request/response model, `gen_ai.token.type` (input/output) |
| `gen_ai.client.operation.duration` | `s` | operation, provider, request/response model, `error.type` |
| `gen_ai.client.operation.time_to_first_chunk` | `s` | operation, provider, request/response model |

Dimensions are bounded, so series count stays flat as conversations grow. Product instruments registered through `get_metrics_collector()` pass through the cardinality firewall (unbounded keys such as session or turn ids are dropped).

---

## Privacy

Telemetry leaves through one door, the `PrivacyGuardExporter` wrapped around the real exporter:

- **Default: metadata only.** Numbers and booleans pass; text passes only under metadata namespaces (`gen_ai.*`, `error.*`, `agent.*`, `http.*`, ...). Prompt, reply, tool arguments and results, exception messages and stack traces, and third-party payload attributes (`input.value`, `llm.input_messages.*`, ...) are withheld.
- **Content capture is opt-in**: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` releases `gen_ai.input.messages`, `gen_ai.output.messages` and tool call arguments/results. The system prompt and model reasoning are never exported, with or without the switch.
- Every text that is kept is credential-redacted and length-capped.
- The guard works on sanitized **copies** of finished spans and fails closed: a span that cannot be sanitized is withheld, never sent raw.

---

## Sampling

Sampling is the SDK's own. The default is parent-based always-on.

```bash
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1     # keep 10% of traces
```

You can also pass a `Sampler` object: `setup_tracing(sampler=...)`.

| Environment | Ratio | Rationale |
|-------------|-------|-----------|
| Development | 1.0 | Debug all requests |
| Staging | 0.5 | Balance coverage and cost |
| Production (low traffic) | 0.1 | Reduce storage 90% |
| Production (high traffic) | 0.01 | Keep 1% of traces |

The GenAI client metrics are recorded from the model call itself, so lowering the trace ratio does not distort token, latency or error figures.

---

## Operational notes

- **Bounded lifecycle**: `force_flush_tracing()`, `shutdown_tracing()`, `flush_observability()` and `shutdown_observability()` run the SDK action on a daemon thread with a deadline, so a hung collector cannot block a request or process exit. Call `shutdown_observability()` from the host's shutdown hook to flush the last batch.
- **Batching**: spans leave through `BatchSpanProcessor` (background thread, bounded queue). Tune with the standard `OTEL_BSP_*` variables.
- **One provider per process**: if the host already installed a TracerProvider, `setup_tracing()` leaves it alone and the posture reports `degraded`.
- **Local development**: `setup_tracing(console_export=True)` prints spans to stdout (only when no OTLP endpoint is configured).

### Cross-service propagation

`inject_trace_context()` and `extract_trace_context()` (`myrm_agent_harness.infra.tracing.propagation`) wrap the standard OpenTelemetry propagation API (W3C `traceparent`). A host that wants one trace across services calls them at its own service boundaries; the framework does not propagate context on its own.

---

## Troubleshooting

**No traces in the backend**

1. `get_telemetry_posture()["status"]`: `ready` means the pipeline is up but nothing has been sent yet (no span has finished, or the first batch is still queued; `active` follows the first accepted batch), `noop` means no endpoint is configured, `disabled` means `OTEL_SDK_DISABLED=true`, `degraded` carries the reason (for example a missing `opentelemetry-exporter-otlp-proto-http`), `failing` means the collector rejected or could not receive the last batch (`last_failure_at`, `failed_batches`).
2. Check the protocol/port pair: HTTP/protobuf is conventionally `:4318`, gRPC `:4317` (an unset protocol is inferred from that port).
3. `MYRM_LOCAL_TRACE_ONLY=1` refuses remote endpoints by design.
4. A sampler of `always_off` or a ratio of `0` drops every trace: the posture shows the active sampler.

**Spans are missing attributes such as prompts**

By design. Content is exported only with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`.

**Spans queued or dropped under load**

The posture counters cover export outcomes only: `exported_spans` and `failed_batches` count what the exporter reported, and `withheld_spans` counts spans the privacy guard could not sanitize and therefore never sent. A span the `BatchSpanProcessor` discards because its queue is full never reaches the guard and appears in no counter.

Enable `OTEL_PYTHON_SDK_INTERNAL_METRICS_ENABLED=true` and watch `otel.sdk.processor.span.queue.size` against `otel.sdk.processor.span.queue.capacity`.

---

## Reference

- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [OTLP exporter configuration](https://opentelemetry.io/docs/specs/otel/protocol/exporter/)
- [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

Framework code:

- `myrm_agent_harness/infra/tracing/tracer.py` - tracer setup and consumer helpers
- `myrm_agent_harness/infra/tracing/gen_ai/` - span tree and GenAI client metrics
- `myrm_agent_harness/infra/tracing/otlp/` - endpoint resolution, exporters, privacy guard, posture
- `myrm_agent_harness/infra/tracing/metrics/exporter.py` - metrics export
