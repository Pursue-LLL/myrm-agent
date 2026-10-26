# gen_ai/

## Overview
The framework side of GenAI telemetry: one span tree per agent run (`invoke_agent {agent}` → `chat {model}` / `execute_tool {tool}`, sub-agents as subtrees) and the three standard GenAI client metrics. It depends on the OpenTelemetry API only, so producers cost nothing without an SDK and never import an exporter. What leaves the process is decided downstream by `otlp/privacy.py`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade: `AgentRunSpan`, `ModelCall`, `execute_tool_span`, `capture_content_enabled`, `conventions`. | ✅ |
| agent_span.py | Core | `invoke_agent` span of one run; current only while a step executes, so nothing leaks across `yield` boundaries; outcome `completed` / `error` / `cancelled`. | ✅ |
| content.py | Core | Opt-in content capture (standard `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`, off by default); message and tool-call serialization; system prompt and reasoning are never included. | ✅ |
| conventions.py | Core | Single naming vocabulary (released GenAI semantic-convention names only), content-key sets read by the privacy guard, span-name builders. | ✅ |
| metrics.py | Core | `gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, `gen_ai.client.operation.time_to_first_chunk`, recorded once per model call and independent of trace sampling. | ✅ |
| model_call.py | Core | `ModelCall`: one `chat` span per logical model call (retries are span events, replayed memo answers create nothing), closed in `finally`; error class recorded, error text is not. | ✅ |
| tool_span.py | Core | `execute_tool_span`: one span per tool call, current while the tool runs so nested sub-agent and model spans parent to it. | ✅ |
