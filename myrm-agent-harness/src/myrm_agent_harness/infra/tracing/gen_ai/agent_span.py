"""One `invoke_agent` span per agent run, current only while the run executes a step.

[INPUT]
- opentelemetry.trace / opentelemetry.context (POS: tracer and context API)
- gen_ai.conventions / gen_ai.content (POS: names and opt-in content)

[OUTPUT]
- AgentRunSpan: span of one agent run; ``scope`` wraps the run's event stream, ``end`` closes it

[POS]
Root of the GenAI span tree for one run (or one sub-agent run under a tool span). The span is made
current only inside each ``__anext__`` of the wrapped event stream and detached before the event
reaches the consumer, so model-call and tool spans created during a step parent to it while the
consumer's own context is never touched across a ``yield``. Tasks spawned during a step inherit
the span as their current span, which is what attaches the executor's work to the run. The
outcome is ``completed``, ``error`` or ``cancelled``; a consumer that stops early is ``cancelled``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping

from opentelemetry import context, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from myrm_agent_harness.infra.tracing.gen_ai.content import capture_content_enabled, query_messages_json
from myrm_agent_harness.infra.tracing.gen_ai.conventions import (
    AGENT_STATUS,
    AGENT_STATUS_CANCELLED,
    AGENT_STATUS_COMPLETED,
    AGENT_STATUS_ERROR,
    ERROR_TYPE,
    GEN_AI_AGENT_ID,
    GEN_AI_AGENT_NAME,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_OPERATION_NAME,
    GEN_AI_TRACER_NAME,
    OP_INVOKE_AGENT,
    agent_span_name,
)

MESSAGE_ID = "agent.message_id"


def _text(context_values: Mapping[str, object] | None, key: str) -> str | None:
    value = (context_values or {}).get(key)
    return str(value) if value else None


class _StepScopedIterator[T]:
    """Async iterator that keeps the run span current for exactly one step at a time."""

    __slots__ = ("_inner", "_owner")

    def __init__(self, owner: AgentRunSpan, inner: AsyncIterator[T]) -> None:
        self._owner = owner
        self._inner = inner

    def __aiter__(self) -> _StepScopedIterator[T]:
        return self

    async def __anext__(self) -> T:
        token = context.attach(trace.set_span_in_context(self._owner.span))
        try:
            return await self._inner.__anext__()
        except StopAsyncIteration:
            self._owner.settle(AGENT_STATUS_COMPLETED)
            raise
        except asyncio.CancelledError:
            self._owner.settle(AGENT_STATUS_CANCELLED)
            raise
        except Exception as exc:
            self._owner.settle(AGENT_STATUS_ERROR, error_type=type(exc).__name__)
            raise
        finally:
            context.detach(token)


class AgentRunSpan:
    """The `invoke_agent` span of one agent run."""

    def __init__(
        self,
        *,
        agent_type: str,
        query: object,
        context_values: Mapping[str, object] | None,
        message_id: str | None,
    ) -> None:
        attributes: dict[str, str] = {
            GEN_AI_OPERATION_NAME: OP_INVOKE_AGENT,
            GEN_AI_AGENT_NAME: agent_type,
        }
        for name, value in (
            (GEN_AI_CONVERSATION_ID, _text(context_values, "session_id")),
            (GEN_AI_AGENT_ID, _text(context_values, "agent_id")),
            (MESSAGE_ID, message_id),
        ):
            if value:
                attributes[name] = value
        if capture_content_enabled():
            attributes[GEN_AI_INPUT_MESSAGES] = query_messages_json(query)
        self.span: Span = trace.get_tracer(GEN_AI_TRACER_NAME).start_span(
            agent_span_name(agent_type), kind=SpanKind.INTERNAL, attributes=attributes
        )
        self._status: str | None = None
        self._error_type: str | None = None

    def scope[T](self, events: AsyncIterator[T]) -> AsyncIterator[T]:
        """Wrap the run's event stream so the span is current while each step executes."""
        return _StepScopedIterator(self, events)

    def settle(self, status: str, *, error_type: str | None = None) -> None:
        """Record the run outcome; the first outcome wins."""
        if self._status is None:
            self._status = status
            self._error_type = error_type

    def end(self) -> None:
        """Close the span; a run abandoned before its stream finished is ``cancelled``."""
        status = self._status or AGENT_STATUS_CANCELLED
        self.span.set_attribute(AGENT_STATUS, status)
        if status == AGENT_STATUS_ERROR and self._error_type:
            self.span.set_attribute(ERROR_TYPE, self._error_type)
            self.span.set_status(Status(StatusCode.ERROR, self._error_type))
        self.span.end()
