"""Unit tests for the generic tracing helpers: tracers, spans, decorators, flush and VCS resource metadata."""

import pytest

from myrm_agent_harness.infra.tracing import (
    force_flush_tracing,
    get_telemetry_posture,
    get_tracer,
    parse_otlp_headers,
    setup_tracing,
    shutdown_tracing,
    trace_async,
    trace_context,
    tracer,
)

from ._receivers import OtlpHttpReceiver


def test_get_tracer_returns_noop_without_setup():
    """get_tracer returns a NoOp tracer when setup_tracing has not been called."""
    assert get_tracer("noop_module") is not None


def test_setup_tracing():
    """Test tracing initialization."""
    setup_tracing(service_name="test-service", console_export=False)

    assert get_tracer("test_module") is not None


def test_trace_context():
    """Test trace context manager."""
    setup_tracing(service_name="test-service", console_export=False)

    with trace_context("test_module", "test_operation", {"key": "value"}) as span:
        assert span is not None
        span.set_attribute("custom", "attribute")


def test_trace_context_with_error():
    """Test trace context with exception."""
    setup_tracing(service_name="test-service", console_export=False)

    with pytest.raises(ValueError), trace_context("test_module", "test_operation"):
        raise ValueError("Test error")


@pytest.mark.asyncio
async def test_trace_async_decorator():
    """Test async function tracing decorator."""
    setup_tracing(service_name="test-service", console_export=False)

    @trace_async()
    async def test_function(arg: str) -> str:
        return arg.upper()

    assert await test_function("hello") == "HELLO"


@pytest.mark.asyncio
async def test_trace_async_with_error():
    """Test async decorator with exception."""
    setup_tracing(service_name="test-service", console_export=False)

    @trace_async()
    async def failing_function() -> None:
        raise ValueError("Test error")

    with pytest.raises(ValueError):
        await failing_function()


@pytest.mark.asyncio
async def test_trace_async_with_kwargs():
    """Test async decorator with kwargs."""
    setup_tracing(service_name="test-service", console_export=False)

    @trace_async()
    async def function_with_kwargs(channel: str, recipient: str) -> str:
        return f"{channel}:{recipient}"

    assert await function_with_kwargs(channel="telegram", recipient="user123") == "telegram:user123"


@pytest.mark.asyncio
async def test_decorated_spans_reach_the_collector_without_argument_values(http_receiver: OtlpHttpReceiver):
    """The decorator's span is exported with counts, while caller-supplied argument text stays local."""
    setup_tracing(service_name="test-service", otlp_endpoint=http_receiver.endpoint)

    @trace_async(span_name="deliver")
    async def deliver(channel: str, recipient: str) -> str:
        return f"{channel}:{recipient}"

    await deliver(channel="telegram", recipient="user-4711")
    assert force_flush_tracing(timeout_ms=5000)

    assert http_receiver.wait_for(lambda: bool(http_receiver.spans()))
    [span] = http_receiver.spans()
    assert span.name == "deliver"
    assert span.attributes["kwargs.count"] == 2
    assert span.attributes["success"] is True
    assert "arg.recipient" not in span.attributes
    assert "user-4711" not in str(span.attributes)


def test_parse_otlp_headers():
    """Test standard W3C/OTel header string parsing."""
    raw = "Authorization=Bearer%20secret-token,X-Custom-Header=value123,InvalidPart"
    headers = parse_otlp_headers(raw)
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-Custom-Header"] == "value123"
    assert "InvalidPart" not in headers


def test_vcs_metadata_injection_in_tracing_resource():
    """Verify VCS git branch and commit metadata is captured into resource and posture."""
    setup_tracing(service_name="test-vcs-svc", console_export=True)

    posture = get_telemetry_posture()
    # If in git repo, git_branch is populated, otherwise None without crash
    assert "git_branch" in posture
    assert "git_commit" in posture
    assert tracer._tracer_provider is not None
    resource_attrs = tracer._tracer_provider.resource.attributes
    assert "service.name" in resource_attrs
    if posture["git_branch"]:
        assert "vcs.ref.head.name" in resource_attrs

    shutdown_tracing()


def test_force_flush_tracing_bounded(http_receiver: OtlpHttpReceiver):
    """force_flush_tracing is False before setup and True once a destination is configured."""
    assert force_flush_tracing() is False

    setup_tracing(service_name="test-flush-tracing", otlp_endpoint=http_receiver.endpoint)
    assert force_flush_tracing(timeout_ms=1000.0) is True
