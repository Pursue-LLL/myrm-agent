"""Trace ids that continue an id the calling application already owns.

A service that hands a request id to its users (response header, error body, logs) can make the
OpenTelemetry trace id the same value, so one id leads from a user's report to the exported trace.
The generator asks the application for its current id whenever a new trace starts and adopts it when
it is a valid W3C trace id. Every other case, and every span id, stays random.

[INPUT]
- opentelemetry.sdk.trace.id_generator (POS: IdGenerator and RandomIdGenerator, optional extra)
- infra.tracing.propagation (POS: parse_trace_id, the one definition of a usable trace id)
- resolve: Callable[[], str | None] supplied by the application (POS: the id of the unit of work being served)

[OUTPUT]
- ContextTraceIdGenerator: IdGenerator to pass to ``setup_tracing(id_generator=...)``

[POS]
Depends on the SDK, so it is deliberately not part of the package facade and a bare install keeps
importing. The framework never installs it; the business layer decides.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator

from myrm_agent_harness.infra.tracing.propagation import parse_trace_id

logger = logging.getLogger(__name__)


class ContextTraceIdGenerator(IdGenerator):
    """Draw the trace id of every new trace from ``resolve``; fall back to a random id.

    Only a root span asks for a trace id (a child continues its parent's), so one request that starts
    several roots yields several local roots under the same trace id.
    """

    def __init__(self, resolve: Callable[[], str | None]) -> None:
        self._resolve = resolve
        self._random = RandomIdGenerator()

    def generate_span_id(self) -> int:
        return self._random.generate_span_id()

    def generate_trace_id(self) -> int:
        try:
            adopted = parse_trace_id(self._resolve())
        except Exception:
            # Runs inside span creation: a faulty resolver must cost an id, never the caller's request.
            logger.warning("Trace id resolver failed; using a random trace id", exc_info=True)
            adopted = None
        return adopted if adopted is not None else self._random.generate_trace_id()
