"""One `execute_tool` span per tool call.

[INPUT]
- opentelemetry.trace (POS: tracer API)
- gen_ai.conventions / gen_ai.content (POS: names and opt-in content)

[OUTPUT]
- execute_tool_span: context manager yielding a ToolSpan for the duration of one tool call
- ToolSpan: mark_error / record_result on the live span

[POS]
The span is current while the tool runs, so a sub-agent or model call started by the tool nests
under it. Failure is recorded as an error class (the exception text is not exported; it can carry
tool arguments). Arguments and results are written only when content capture is switched on.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from myrm_agent_harness.infra.tracing.gen_ai.content import (
    capture_content_enabled,
    tool_arguments_json,
    tool_result_text,
)
from myrm_agent_harness.infra.tracing.gen_ai.conventions import (
    ERROR_TYPE,
    GEN_AI_OPERATION_NAME,
    GEN_AI_TOOL_CALL_ARGUMENTS,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_CALL_RESULT,
    GEN_AI_TOOL_NAME,
    GEN_AI_TOOL_TYPE,
    GEN_AI_TRACER_NAME,
    OP_EXECUTE_TOOL,
    TOOL_TYPE_FUNCTION,
    tool_span_name,
)


class ToolSpan:
    """Handle on the live `execute_tool` span."""

    __slots__ = ("_span",)

    def __init__(self, span: Span) -> None:
        self._span = span

    def mark_error(self, error_type: str) -> None:
        self._span.set_attribute(ERROR_TYPE, error_type)
        self._span.set_status(Status(StatusCode.ERROR, error_type))

    def record_result(self, content: object) -> None:
        if capture_content_enabled():
            self._span.set_attribute(GEN_AI_TOOL_CALL_RESULT, tool_result_text(content))


@contextmanager
def execute_tool_span(
    *,
    name: str,
    call_id: str | None,
    arguments: Mapping[str, object],
) -> Iterator[ToolSpan]:
    """Open the span of one tool call; an escaping exception marks it as an error."""
    attributes: dict[str, str] = {
        GEN_AI_OPERATION_NAME: OP_EXECUTE_TOOL,
        GEN_AI_TOOL_NAME: name,
        GEN_AI_TOOL_TYPE: TOOL_TYPE_FUNCTION,
    }
    if call_id:
        attributes[GEN_AI_TOOL_CALL_ID] = call_id
    if capture_content_enabled():
        attributes[GEN_AI_TOOL_CALL_ARGUMENTS] = tool_arguments_json(arguments)
    tracer = trace.get_tracer(GEN_AI_TRACER_NAME)
    with tracer.start_as_current_span(
        tool_span_name(name),
        kind=SpanKind.INTERNAL,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        handle = ToolSpan(span)
        try:
            yield handle
        except Exception as exc:
            handle.mark_error(type(exc).__name__)
            raise
