"""OpenTelemetry tracer setup and consumer helpers.

Framework design:
- ``get_tracer`` / ``trace_async`` / ``trace_context`` are consumer APIs for framework internals.
  They work with OpenTelemetry's default NoOp provider when no TracerProvider is configured,
  producing zero overhead.
- ``setup_tracing`` is a convenience function for the business layer. The framework never calls
  it automatically.
- Enablement follows the standard environment: an OTLP endpoint (the ``otlp_endpoint`` argument,
  ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` or ``OTEL_EXPORTER_OTLP_ENDPOINT``) turns export on,
  ``OTEL_SDK_DISABLED=true`` turns it off, and ``OTEL_TRACES_SAMPLER`` with ``OTEL_TRACES_SAMPLER_ARG``
  chooses sampling.

[INPUT]
- opentelemetry.sdk (POS: provider and batch processor, optional extra)
- infra.tracing.otlp (POS: target resolution, official exporters, privacy guard, resource, posture)

[OUTPUT]
- setup_tracing: initialize tracing (called by the business layer)
- is_tracing_initialized / get_telemetry_posture: live state and measured posture
- get_tracer / trace_async / trace_context: consumer helpers for framework internals
- force_flush_tracing / shutdown_tracing / flush_observability / shutdown_observability: bounded lifecycle
- is_local_trace_only / assert_local_trace_only / parse_otlp_headers: re-exported from otlp.config

[POS]
Tracer utilities. A pipeline exists only when something will actually receive spans; the exporter
is always wrapped by the privacy guard, so nothing leaves the process unsanitized.
"""

from __future__ import annotations

import functools
import importlib.util
import logging
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span

from myrm_agent_harness.infra.tracing.otlp.config import (
    PROTOCOL_HTTP,
    apply_local_isolation,
    assert_local_trace_only,
    is_local_trace_only,
    parse_otlp_headers,
    redact_endpoint,
    resolve_target,
    sdk_disabled,
)
from myrm_agent_harness.infra.tracing.otlp.lifecycle import run_bounded
from myrm_agent_harness.infra.tracing.otlp.posture import (
    EXPORTER_CONSOLE,
    EXPORTER_OTLP_GRPC,
    EXPORTER_OTLP_HTTP,
    build_posture,
    record_traces,
    record_traces_degraded,
    reset_traces,
)

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import Sampler

HAS_OTEL_SDK = importlib.util.find_spec("opentelemetry.sdk") is not None

logger = logging.getLogger(__name__)

_tracer_provider: TracerProvider | None = None
_initialized = False

P = ParamSpec("P")
T = TypeVar("T")

__all__ = [
    "HAS_OTEL_SDK",
    "assert_local_trace_only",
    "flush_observability",
    "force_flush_tracing",
    "get_telemetry_posture",
    "get_tracer",
    "is_local_trace_only",
    "is_tracing_initialized",
    "parse_otlp_headers",
    "setup_tracing",
    "shutdown_observability",
    "shutdown_tracing",
    "trace_async",
    "trace_context",
]


def get_telemetry_posture() -> dict[str, object]:
    """Return the measured posture of the tracing and metric pipelines.

    Safe for SRE health probes, diagnostic status cards and administrative introspection: every
    field comes from live state (see ``otlp.posture``), and the endpoint is credential-redacted.
    """
    return build_posture(initialized=_initialized, has_sdk=HAS_OTEL_SDK)


def setup_tracing(
    service_name: str = "myrm-agent-harness",
    console_export: bool = False,
    otlp_endpoint: str | None = None,
    otlp_headers: dict[str, str] | str | None = None,
    otlp_protocol: str | None = None,
    local_trace_only: bool = False,
    sampler: Sampler | None = None,
    resource_attributes: Mapping[str, str] | None = None,
) -> None:
    """Initialize OpenTelemetry tracing.

    This is a convenience function intended for the business layer. The framework never calls it
    automatically; without a pipeline OpenTelemetry keeps its NoOp provider (zero overhead).

    Args:
        service_name: Default ``service.name`` (``OTEL_SERVICE_NAME`` wins when set).
        console_export: Print spans to stdout (development). Ignored when an OTLP endpoint is set.
        otlp_endpoint: Explicit endpoint; otherwise the standard ``OTEL_EXPORTER_OTLP_*`` variables.
        otlp_headers: Explicit headers (dict or ``k=v,k2=v2``); otherwise ``OTEL_EXPORTER_OTLP_HEADERS``.
        otlp_protocol: ``http/protobuf`` or ``grpc``; otherwise the standard variables, then HTTP.
        local_trace_only: Refuse remote export (also enforced by ``MYRM_LOCAL_TRACE_ONLY``).
        sampler: Optional SDK sampler; otherwise ``OTEL_TRACES_SAMPLER`` / ``OTEL_TRACES_SAMPLER_ARG``,
            default parent-based always-on.
        resource_attributes: Default resource attributes (``OTEL_RESOURCE_ATTRIBUTES`` wins).

    A requested protocol that cannot be served (missing exporter package) leaves tracing off and is
    reported by the posture probe; it never falls back to another protocol or to stdout.
    """
    global _tracer_provider, _initialized

    target = apply_local_isolation(
        resolve_target("traces", endpoint=otlp_endpoint, protocol=otlp_protocol, headers=otlp_headers),
        requested=local_trace_only,
    )

    if not HAS_OTEL_SDK:
        logger.warning("OpenTelemetry SDK not installed. Tracing runs in NoOp mode. Install the `observability` extra.")
        return
    if sdk_disabled():
        logger.info("OTEL_SDK_DISABLED is set: tracing stays off")
        return
    if _initialized:
        logger.warning("Tracing already initialized")
        return
    if target is None and not console_export:
        logger.debug("No OTLP endpoint configured: tracing stays off")
        return

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    from myrm_agent_harness.infra.tracing.otlp.exporters import OtlpUnavailableError, create_span_exporter
    from myrm_agent_harness.infra.tracing.otlp.privacy import PrivacyGuardExporter
    from myrm_agent_harness.infra.tracing.otlp.resource import (
        VCS_REF_HEAD_NAME,
        VCS_REPOSITORY_CHANGE_ID,
        build_resource,
    )

    if target is not None:
        try:
            exporter = create_span_exporter(target)
        except OtlpUnavailableError as exc:
            logger.warning("OTLP trace export unavailable, tracing stays off: %s", exc)
            record_traces_degraded(target=target, reason=str(exc))
            return
        exporter_type = EXPORTER_OTLP_HTTP if target.protocol == PROTOCOL_HTTP else EXPORTER_OTLP_GRPC
    else:
        exporter, exporter_type = ConsoleSpanExporter(), EXPORTER_CONSOLE

    resource = build_resource(service_name, resource_attributes)
    provider = TracerProvider(resource=resource, sampler=sampler)
    guard = PrivacyGuardExporter(exporter)
    provider.add_span_processor(BatchSpanProcessor(guard))

    trace.set_tracer_provider(provider)
    if trace.get_tracer_provider() is not provider:
        provider.shutdown()
        reason = "another TracerProvider is already installed in this process"
        logger.warning("Tracing not installed: %s", reason)
        record_traces_degraded(target=target, reason=reason)
        return

    _tracer_provider = provider
    _initialized = True
    commit = resource.attributes.get(VCS_REPOSITORY_CHANGE_ID)
    branch = resource.attributes.get(VCS_REF_HEAD_NAME)
    record_traces(
        target=target,
        exporter_type=exporter_type,
        sampler=provider.sampler.get_description(),
        git_branch=str(branch) if branch else None,
        git_commit=str(commit) if commit else None,
        stats=guard.stats,
    )
    logger.info(
        "Tracing initialized: service=%s exporter=%s endpoint=%s sampler=%s",
        service_name,
        exporter_type,
        redact_endpoint(target.endpoint) if target else "stdout",
        provider.sampler.get_description(),
    )


def is_tracing_initialized() -> bool:
    """Return True when ``setup_tracing()`` has configured a real TracerProvider."""
    return _initialized


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance (NoOp until ``setup_tracing()`` installs a provider)."""
    return trace.get_tracer(name)


@contextmanager
def trace_context(
    tracer_name: str,
    span_name: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> Iterator[Span]:
    """Context manager for creating a span.

    Example:
        with trace_context("my_module", "operation", {"key": "value"}):
            pass
    """
    with get_tracer(tracer_name).start_as_current_span(span_name) as span:
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__name__)
            span.record_exception(exc)
            raise


def trace_async(
    tracer_name: str | None = None,
    span_name: str | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator for tracing async functions.

    Example:
        @trace_async()
        async def my_function(arg: str) -> str:
            return arg.upper()
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            tracer = get_tracer(tracer_name or func.__module__)
            with tracer.start_as_current_span(span_name or func.__name__) as span:
                if args:
                    span.set_attribute("args.count", len(args))
                if kwargs:
                    span.set_attribute("kwargs.count", len(kwargs))
                    for key in ("channel", "recipient", "model", "provider"):
                        if key in kwargs:
                            span.set_attribute(f"arg.{key}", str(kwargs[key]))
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as exc:
                    span.set_attribute("error.type", type(exc).__name__)
                    span.record_exception(exc)
                    raise

        return wrapper

    return decorator


def force_flush_tracing(timeout_ms: float = 1500.0) -> bool:
    """Flush the tracer provider with a deadline; False when uninitialized, late or failed."""
    if not _initialized or _tracer_provider is None:
        return False
    return run_bounded(
        _tracer_provider.force_flush,
        thread_name="otel-tracing-bounded-flush",
        timeout_ms=timeout_ms,
        label="tracing force_flush",
    )


def shutdown_tracing(timeout_ms: float = 1500.0) -> bool:
    """Shut the tracer provider down with a deadline so a hung collector cannot block process exit."""
    global _tracer_provider, _initialized

    if not _initialized or _tracer_provider is None:
        return False
    provider = _tracer_provider
    _tracer_provider = None
    _initialized = False
    reset_traces()
    done = run_bounded(
        provider.shutdown,
        thread_name="otel-bounded-shutdown",
        timeout_ms=timeout_ms,
        label="tracing provider shutdown",
    )
    if done:
        logger.info("Tracing provider shutdown complete")
    return done


def _run_both_channels(tracing: Callable[[], bool], metrics: Callable[[], bool], prefix: str) -> dict[str, bool]:
    """Run the tracing and metrics actions concurrently so one hung channel cannot delay the other."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, bool] = {"tracing": False, "metrics": False}

    def _safe(action: Callable[[], bool]) -> bool:
        try:
            return action()
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix=prefix) as executor:
        futures = {executor.submit(_safe, tracing): "tracing", executor.submit(_safe, metrics): "metrics"}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def flush_observability(timeout_ms: float = 1500.0) -> dict[str, bool]:
    """Flush tracing and metrics concurrently within one bounded timeout."""

    def _flush_metrics() -> bool:
        from myrm_agent_harness.infra.tracing.metrics.exporter import force_flush_metrics

        return force_flush_metrics(timeout_ms=timeout_ms)

    return _run_both_channels(lambda: force_flush_tracing(timeout_ms), _flush_metrics, "otel-dual-flush")


def shutdown_observability(timeout_ms: float = 1500.0) -> dict[str, bool]:
    """Shut tracing and metrics down concurrently within one bounded timeout."""

    def _shutdown_metrics() -> bool:
        from myrm_agent_harness.infra.tracing.metrics.exporter import shutdown_metrics

        return shutdown_metrics(timeout_ms=timeout_ms)

    return _run_both_channels(lambda: shutdown_tracing(timeout_ms), _shutdown_metrics, "otel-dual-shutdown")
