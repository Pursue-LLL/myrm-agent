"""Trace ids that continue an application-owned id: the generator, a real provider and the OTLP wire."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import format_trace_id

from myrm_agent_harness.infra.tracing import force_flush_tracing, setup_tracing, trace_context
from myrm_agent_harness.infra.tracing.id_generator import ContextTraceIdGenerator

from ._receivers import OtlpHttpReceiver

_ADOPTED = "4bf92f3577b34da6a3ce929d0e0e4736"
_OTHER = "0af7651916cd43dd8448eb211c80319c"
_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)


@pytest.fixture(autouse=True)
def _no_request() -> None:
    _REQUEST_ID.set(None)


def test_a_valid_id_becomes_the_trace_id() -> None:
    assert ContextTraceIdGenerator(lambda: _ADOPTED).generate_trace_id() == int(_ADOPTED, 16)


def test_upper_case_hex_is_adopted_and_formats_to_the_lower_case_form() -> None:
    adopted = ContextTraceIdGenerator(lambda: _ADOPTED.upper()).generate_trace_id()

    assert format_trace_id(adopted) == _ADOPTED


@pytest.mark.parametrize(
    "unusable",
    [None, "", "-", "abc", _ADOPTED[:-1], _ADOPTED + "0", "0" * 32, "g" * 32, f" {_ADOPTED[:-1]}", f"{_ADOPTED}\n"],
)
def test_an_unusable_id_gives_a_random_one(unusable: str | None) -> None:
    generator = ContextTraceIdGenerator(lambda: unusable)

    first, second = generator.generate_trace_id(), generator.generate_trace_id()

    assert 0 < first < 2**128
    assert first != second


def test_span_ids_stay_random_and_never_consult_the_resolver() -> None:
    resolve = MagicMock(return_value=_ADOPTED)
    generator = ContextTraceIdGenerator(resolve)

    span_ids = {generator.generate_span_id() for _ in range(50)}

    resolve.assert_not_called()
    assert len(span_ids) == 50
    assert all(0 < span_id < 2**64 for span_id in span_ids)


def test_a_failing_resolver_costs_the_id_never_the_request(caplog: pytest.LogCaptureFixture) -> None:
    def broken() -> str | None:
        raise RuntimeError("resolver is down")

    with caplog.at_level(logging.WARNING, logger="myrm_agent_harness.infra.tracing.id_generator"):
        trace_id = ContextTraceIdGenerator(broken).generate_trace_id()

    assert 0 < trace_id < 2**128
    assert "Trace id resolver failed" in caplog.text


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(id_generator=ContextTraceIdGenerator(_REQUEST_ID.get))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_roots_started_while_a_request_is_served_share_its_id_and_children_follow() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer("tests")
    _REQUEST_ID.set(_ADOPTED)

    with tracer.start_as_current_span("first-root"), tracer.start_as_current_span("child"):
        pass
    with tracer.start_as_current_span("second-root"):
        pass

    trace_ids = {span.name: format_trace_id(span.context.trace_id) for span in exporter.get_finished_spans()}
    assert trace_ids == {"first-root": _ADOPTED, "child": _ADOPTED, "second-root": _ADOPTED}


def test_outside_a_request_every_trace_gets_its_own_random_id() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer("tests")

    with tracer.start_as_current_span("background-a"):
        pass
    with tracer.start_as_current_span("background-b"):
        pass

    first, second = (span.context.trace_id for span in exporter.get_finished_spans())
    assert first != second
    assert _ADOPTED not in {format_trace_id(first), format_trace_id(second)}


def test_a_child_keeps_its_parents_trace_even_when_the_request_id_changes() -> None:
    provider, exporter = _provider()
    tracer = provider.get_tracer("tests")
    _REQUEST_ID.set(_ADOPTED)

    with tracer.start_as_current_span("parent"):
        _REQUEST_ID.set(_OTHER)
        with tracer.start_as_current_span("child"):
            pass

    assert {format_trace_id(span.context.trace_id) for span in exporter.get_finished_spans()} == {_ADOPTED}


def test_setup_tracing_exports_the_adopted_id_on_the_wire(http_receiver: OtlpHttpReceiver) -> None:
    setup_tracing(
        service_name="svc-ids",
        otlp_endpoint=http_receiver.endpoint,
        id_generator=ContextTraceIdGenerator(_REQUEST_ID.get),
    )
    _REQUEST_ID.set(_ADOPTED)

    with trace_context("tests.ids", "agent.run", {}):
        pass
    assert force_flush_tracing(timeout_ms=5000)

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    span = http_receiver.spans()[0]
    assert (span.name, span.trace_id, span.parent_span_id) == ("agent.run", _ADOPTED, "")
