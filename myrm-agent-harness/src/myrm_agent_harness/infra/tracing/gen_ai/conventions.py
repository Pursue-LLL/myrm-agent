"""OpenTelemetry GenAI semantic-convention names used by every Myrm span and metric.

[INPUT]
- (none: plain string constants, importable without the OpenTelemetry SDK)

[OUTPUT]
- GEN_AI_TRACER_NAME: instrumentation scope shared by agent, model-call and tool spans
- OP_* / GEN_AI_* / ERROR_TYPE: released GenAI attribute names and ``gen_ai.operation.name`` values
- METRIC_*: the three standard GenAI client metric names
- CONTENT_ATTRIBUTES / CONTENT_ATTRIBUTE_PREFIXES: attributes that carry user or model content
- agent_span_name / chat_span_name / tool_span_name: span-name builders

[POS]
Single source of truth for GenAI telemetry vocabulary. Only names released in the OpenTelemetry
GenAI semantic conventions appear here (one naming set, no experimental duplicates), so every
backend that understands the standard renders Myrm traces without a mapping layer. The exporter's
privacy guard reads the content-key sets from here, which keeps "what is content" next to the
names that are written.
"""

from __future__ import annotations

GEN_AI_TRACER_NAME = "myrm_agent_harness.gen_ai"

# ``gen_ai.operation.name`` values
OP_CHAT = "chat"
OP_INVOKE_AGENT = "invoke_agent"
OP_EXECUTE_TOOL = "execute_tool"

# Identity
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"

# Model request / response
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_STREAM = "gen_ai.request.stream"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_RESPONSE_TIME_TO_FIRST_CHUNK = "gen_ai.response.time_to_first_chunk"

# Token accounting. Input includes cache read and cache write tokens, as the convention defines.
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = "gen_ai.usage.cache_creation.input_tokens"
GEN_AI_USAGE_REASONING_OUTPUT_TOKENS = "gen_ai.usage.reasoning.output_tokens"

# Tools
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
TOOL_TYPE_FUNCTION = "function"

# Content (written only when content capture is switched on)
GEN_AI_INPUT_MESSAGES = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"
GEN_AI_TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
GEN_AI_TOOL_CALL_RESULT = "gen_ai.tool.call.result"
GEN_AI_SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"

# Errors and metric dimensions
ERROR_TYPE = "error.type"
GEN_AI_TOKEN_TYPE = "gen_ai.token.type"
TOKEN_TYPE_INPUT = "input"
TOKEN_TYPE_OUTPUT = "output"

# Product-owned run outcome on the agent span
AGENT_STATUS = "agent.status"
AGENT_STATUS_COMPLETED = "completed"
AGENT_STATUS_ERROR = "error"
AGENT_STATUS_CANCELLED = "cancelled"

# Standard GenAI client metrics
METRIC_TOKEN_USAGE = "gen_ai.client.token.usage"
METRIC_OPERATION_DURATION = "gen_ai.client.operation.duration"
METRIC_TIME_TO_FIRST_CHUNK = "gen_ai.client.operation.time_to_first_chunk"

# Attributes that carry user or model content. The privacy guard withholds them unless content
# capture is switched on; the system prompt is withheld even then.
CONTENT_ATTRIBUTES: frozenset[str] = frozenset(
    {
        GEN_AI_INPUT_MESSAGES,
        GEN_AI_OUTPUT_MESSAGES,
        GEN_AI_TOOL_CALL_ARGUMENTS,
        GEN_AI_TOOL_CALL_RESULT,
        GEN_AI_SYSTEM_INSTRUCTIONS,
        "gen_ai.tool.definitions",
        "gen_ai.retrieval.query.text",
        "gen_ai.retrieval.documents",
        "gen_ai.evaluation.explanation",
        "gen_ai.prompt",
        "gen_ai.completion",
        # Exception text can echo the input that caused it; the exception class stays exported.
        "exception.message",
        "exception.stacktrace",
        "error.message",
    }
)
CONTENT_ATTRIBUTE_PREFIXES: tuple[str, ...] = ("gen_ai.prompt.", "gen_ai.completion.")
NEVER_EXPORTED_ATTRIBUTES: frozenset[str] = frozenset({GEN_AI_SYSTEM_INSTRUCTIONS})


def agent_span_name(agent_type: str) -> str:
    return f"{OP_INVOKE_AGENT} {agent_type}"


def chat_span_name(model: str) -> str:
    return f"{OP_CHAT} {model}"


def tool_span_name(tool_name: str) -> str:
    return f"{OP_EXECUTE_TOOL} {tool_name}"
