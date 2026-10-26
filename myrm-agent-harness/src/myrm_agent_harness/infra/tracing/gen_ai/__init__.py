"""GenAI span tree and client metrics: invoke_agent -> chat / execute_tool.

[INPUT]
- gen_ai.agent_span / model_call / tool_span / metrics / content / conventions (POS: submodules below)

[OUTPUT]
- AgentRunSpan: span of one agent run
- ModelCall: span and metrics of one logical model call
- execute_tool_span: span of one tool call
- capture_content_enabled: whether message and tool content may be written onto spans
- conventions: the single naming vocabulary (import as ``gen_ai.conventions``)

[POS]
The framework side of GenAI telemetry. It depends only on the OpenTelemetry API, so producers cost
nothing without an SDK and never import an exporter. What leaves the process is decided downstream
by ``otlp.privacy``.
"""

from myrm_agent_harness.infra.tracing.gen_ai.agent_span import AgentRunSpan
from myrm_agent_harness.infra.tracing.gen_ai.content import capture_content_enabled
from myrm_agent_harness.infra.tracing.gen_ai.model_call import ModelCall, provider_name
from myrm_agent_harness.infra.tracing.gen_ai.tool_span import ToolSpan, execute_tool_span

__all__ = [
    "AgentRunSpan",
    "ModelCall",
    "ToolSpan",
    "capture_content_enabled",
    "execute_tool_span",
    "provider_name",
]
