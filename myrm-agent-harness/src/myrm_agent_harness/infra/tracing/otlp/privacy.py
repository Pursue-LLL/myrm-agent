"""Exporter-boundary privacy guard: nothing leaves the process that was not cleared here.

[INPUT]
- opentelemetry.sdk.trace (ReadableSpan, Event) / opentelemetry.trace (Link, Status)
- infra.tracing.sanitizer::TraceSpanSanitizer (POS: credential redaction, bounded truncation)
- gen_ai.conventions / gen_ai.content (POS: content attribute names, capture switch)
- otlp.stats::ExportStats (POS: measured export outcome read by the posture probe)

[OUTPUT]
- sanitize_span: a sanitized copy of one finished span (attributes, events, links, status)
- PrivacyGuardExporter: SpanExporter wrapper that sanitizes every batch and counts what happened

[POS]
Telemetry leaves through one door. By default only metadata crosses it: numbers and booleans, plus
text under metadata namespaces. Prompt, reply, tool arguments and results, and any third-party
payload attribute (``input.value``, ``llm.input_messages.*``, ``metadata`` ...) are withheld unless
the standard ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` switch is on, and the system
prompt is never exported. Every kept text still passes credential redaction and a length cap.
Sanitizing builds copies through the public ``ReadableSpan`` constructor (finished spans are not
mutated) and fails closed: a span that cannot be sanitized is dropped, never sent raw.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Mapping, Sequence

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Link
from opentelemetry.trace.status import Status, StatusCode

from myrm_agent_harness.infra.tracing.gen_ai.content import CONTENT_VALUE_LIMIT, capture_content_enabled
from myrm_agent_harness.infra.tracing.gen_ai.conventions import (
    CONTENT_ATTRIBUTE_PREFIXES,
    CONTENT_ATTRIBUTES,
    NEVER_EXPORTED_ATTRIBUTES,
)
from myrm_agent_harness.infra.tracing.otlp.stats import ExportStats
from myrm_agent_harness.infra.tracing.sanitizer import AttributeValue, TraceSpanSanitizer

logger = logging.getLogger(__name__)

# Namespaces whose text values describe the operation, not its content.
_METADATA_PREFIXES: tuple[str, ...] = (
    "gen_ai.",
    "error.",
    "exception.",
    "agent.",
    "fallback.",
    "retry.",
    "decision.",
    "myrm.",
    "http.",
    "rpc.",
    "server.",
    "network.",
    "code.",
)

_METADATA_SANITIZER = TraceSpanSanitizer()
_CONTENT_SANITIZER = TraceSpanSanitizer(max_value_len=CONTENT_VALUE_LIMIT)
_DROP_LOG_EVERY = 100
_CLASS_NAME = re.compile(r"[A-Za-z_][\w.]*")


def _is_content_key(key: str) -> bool:
    return key in CONTENT_ATTRIBUTES or key.startswith(CONTENT_ATTRIBUTE_PREFIXES)


def _is_text(value: object) -> bool:
    """True when the value can carry content: text, a sequence holding text, or anything non-scalar."""
    if isinstance(value, (bool, int, float)):
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_is_text(item) for item in value)
    return True


def _is_exported(key: str, value: object, *, capture_content: bool) -> bool:
    if key in NEVER_EXPORTED_ATTRIBUTES:
        return False
    if not _is_text(value):
        return True
    if _is_content_key(key):
        return capture_content
    return capture_content or key.startswith(_METADATA_PREFIXES)


def _clean_attributes(
    attributes: Mapping[str, object] | None,
    *,
    capture_content: bool,
) -> dict[str, AttributeValue]:
    cleaned: dict[str, AttributeValue] = {}
    for key, value in (attributes or {}).items():
        if not _is_exported(key, value, capture_content=capture_content):
            continue
        sanitizer = _CONTENT_SANITIZER if capture_content and _is_content_key(key) else _METADATA_SANITIZER
        cleaned[key] = sanitizer.sanitize_attribute(key, value)
    return cleaned


def _clean_status(status: Status, *, capture_content: bool) -> Status:
    """Keep an error description only as a bare class name unless content capture is on.

    ``start_as_current_span`` writes ``"<Class>: <message>"``; the message may echo the input.
    """
    if status.status_code is not StatusCode.ERROR or not status.description:
        return Status(status.status_code)
    if capture_content:
        return Status(StatusCode.ERROR, _CONTENT_SANITIZER.sanitize_string_value(status.description))
    class_name = status.description.partition(":")[0].strip()
    return Status(StatusCode.ERROR, class_name if _CLASS_NAME.fullmatch(class_name) else None)


def sanitize_span(span: ReadableSpan, *, capture_content: bool) -> ReadableSpan:
    """Return a sanitized copy of ``span``; the finished span itself is left untouched."""
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=_clean_attributes(span.attributes, capture_content=capture_content),
        events=tuple(
            Event(
                name=event.name,
                attributes=_clean_attributes(event.attributes, capture_content=capture_content),
                timestamp=event.timestamp,
            )
            for event in span.events
        ),
        links=tuple(
            Link(link.context, _clean_attributes(link.attributes, capture_content=capture_content))
            for link in span.links
        ),
        kind=span.kind,
        status=_clean_status(span.status, capture_content=capture_content),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class PrivacyGuardExporter(SpanExporter):
    """Wraps an exporter: sanitizes each batch on the way out and records the outcome."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner
        self._lock = threading.Lock()
        self._stats = ExportStats()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        capture_content = capture_content_enabled()
        safe: list[ReadableSpan] = []
        dropped = 0
        for span in spans:
            try:
                safe.append(sanitize_span(span, capture_content=capture_content))
            except Exception:
                logger.debug("Span sanitization failed; the span is dropped", exc_info=True)
                dropped += 1
        if dropped:
            self._record_dropped(dropped)
        if not safe:
            return SpanExportResult.SUCCESS
        try:
            result = self._inner.export(safe)
        except Exception as exc:
            logger.warning("OTLP span export raised %s", type(exc).__name__)
            result = SpanExportResult.FAILURE
        self._record_result(result, len(safe))
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)

    def stats(self) -> ExportStats:
        with self._lock:
            return self._stats

    def _record_dropped(self, count: int) -> None:
        with self._lock:
            before = self._stats.dropped_spans
            self._stats = ExportStats(
                self._stats.exported_spans,
                self._stats.failed_batches,
                before + count,
                self._stats.last_success_at,
                self._stats.last_failure_at,
            )
        if before == 0 or (before + count) // _DROP_LOG_EVERY > before // _DROP_LOG_EVERY:
            logger.warning(
                "Dropped %d span(s) that could not be sanitized (%d dropped in total)", count, before + count
            )

    def _record_result(self, result: SpanExportResult, count: int) -> None:
        now = time.time()
        with self._lock:
            stats = self._stats
            if result is SpanExportResult.SUCCESS:
                self._stats = ExportStats(
                    stats.exported_spans + count,
                    stats.failed_batches,
                    stats.dropped_spans,
                    now,
                    stats.last_failure_at,
                )
            else:
                self._stats = ExportStats(
                    stats.exported_spans,
                    stats.failed_batches + 1,
                    stats.dropped_spans,
                    stats.last_success_at,
                    now,
                )
