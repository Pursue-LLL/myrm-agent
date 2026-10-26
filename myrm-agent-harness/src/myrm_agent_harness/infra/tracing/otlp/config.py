"""OTLP target resolution and the local-trace-only isolation gate.

[INPUT]
- os.environ: standard ``OTEL_EXPORTER_OTLP_*`` variables (per-signal and general)
- core.security.redact.engine::redact_sensitive_text (POS: credential scrubbing for displayed endpoints)

[OUTPUT]
- OtlpTarget / resolve_target: where one signal is exported, resolved like the OpenTelemetry spec
- parse_otlp_headers: W3C key=value header list parsing
- configured_endpoints: every endpoint the environment names (for audits)
- redact_endpoint: endpoint safe to log and show (no credentials)
- is_local_trace_only / is_local_endpoint / assert_local_trace_only / apply_local_isolation: zero-egress gate

[POS]
Pure configuration logic (no SDK import). A general ``OTEL_EXPORTER_OTLP_ENDPOINT`` is a base URL
that gets ``/v1/traces`` or ``/v1/metrics`` appended for HTTP/protobuf (a base that already ends
with the signal path is used as is); a signal-specific URL is used verbatim; gRPC takes the endpoint
as given. ``OTEL_TRACES_EXPORTER=none`` / ``OTEL_METRICS_EXPORTER=none`` switch one signal off.
The same rules serve the span exporter, the metric exporter, the posture probe and the isolation
gate, so what is displayed is what is dialled.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Literal

from myrm_agent_harness.core.security.redact.engine import redact_sensitive_text

logger = logging.getLogger(__name__)

type Signal = Literal["traces", "metrics"]

PROTOCOL_HTTP = "http/protobuf"
PROTOCOL_GRPC = "grpc"
DEFAULT_PROTOCOL = PROTOCOL_HTTP

_SIGNAL_ENV_KEY: dict[Signal, str] = {"traces": "TRACES", "metrics": "METRICS"}
_SIGNAL_PATH: dict[Signal, str] = {"traces": "v1/traces", "metrics": "v1/metrics"}
_TRUTHY = frozenset({"1", "true", "yes", "on"})
# ``user:password@`` after the scheme separator (or leading a scheme-less target), well-formed or not.
_USERINFO = re.compile(r"(?:(?<=//)|^)[^/@\s]*@")


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def sdk_disabled() -> bool:
    """True when the standard ``OTEL_SDK_DISABLED`` kill switch is set."""
    return _env("OTEL_SDK_DISABLED").lower() == "true"


@dataclass(frozen=True, slots=True)
class OtlpTarget:
    """One signal's resolved export destination."""

    signal: Signal
    endpoint: str
    protocol: str
    headers: dict[str, str] | None
    headers_configured: bool


def parse_otlp_headers(raw_headers: str | None = None) -> dict[str, str]:
    """Parse a W3C / OpenTelemetry ``key1=value1,key2=value2`` header list (URL-decoded)."""
    raw = raw_headers if raw_headers is not None else _env("OTEL_EXPORTER_OTLP_HEADERS")
    headers: dict[str, str] = {}
    for part in raw.split(","):
        key, separator, value = part.partition("=")
        key = urllib.parse.unquote(key.strip())
        if separator and key:
            headers[key] = urllib.parse.unquote(value.strip())
    return headers


def _signal_url(base: str, signal: Signal, protocol: str) -> str:
    if protocol == PROTOCOL_GRPC:
        return base
    path = _SIGNAL_PATH[signal]
    trimmed = base.rstrip("/")
    return trimmed if trimmed.endswith(f"/{path}") else f"{trimmed}/{path}"


def resolve_target(
    signal: Signal,
    *,
    endpoint: str | None = None,
    protocol: str | None = None,
    headers: dict[str, str] | str | None = None,
) -> OtlpTarget | None:
    """Resolve where ``signal`` is exported, or None when no endpoint is configured.

    ``endpoint`` has the semantics of ``OTEL_EXPORTER_OTLP_ENDPOINT`` (a base URL) and wins over the
    environment; otherwise the signal-specific variable (verbatim) precedes the general one. An
    environment-selected destination is switched off by ``OTEL_<SIGNAL>_EXPORTER=none``; an explicit
    ``endpoint`` is a deliberate choice of the caller and is not.
    """
    key = _SIGNAL_ENV_KEY[signal]
    explicit_endpoint = bool(endpoint and endpoint.strip())
    if not explicit_endpoint and _env(f"OTEL_{key}_EXPORTER").lower() == "none":
        return None
    resolved_protocol = (
        protocol
        or _env(f"OTEL_EXPORTER_OTLP_{key}_PROTOCOL")
        or _env("OTEL_EXPORTER_OTLP_PROTOCOL")
        or DEFAULT_PROTOCOL
    ).lower()

    if endpoint and explicit_endpoint:
        url = _signal_url(endpoint.strip(), signal, resolved_protocol)
    elif signal_specific := _env(f"OTEL_EXPORTER_OTLP_{key}_ENDPOINT"):
        url = signal_specific
    elif general := _env("OTEL_EXPORTER_OTLP_ENDPOINT"):
        url = _signal_url(general, signal, resolved_protocol)
    else:
        return None

    explicit = parse_otlp_headers(headers) if isinstance(headers, str) else dict(headers or {})
    from_env = bool(_env(f"OTEL_EXPORTER_OTLP_{key}_HEADERS") or _env("OTEL_EXPORTER_OTLP_HEADERS"))
    return OtlpTarget(
        signal=signal,
        endpoint=url,
        protocol=resolved_protocol,
        headers=explicit or None,
        headers_configured=bool(explicit) or from_env,
    )


def configured_endpoints() -> list[str]:
    """Every endpoint the environment names, whether or not its signal is switched on.

    For audits: an exporter switched off today can be switched on by one variable, so the
    configuration itself is what a zero-egress policy has to vouch for.
    """
    names = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    return [value for name in names if (value := _env(name))]


def redact_endpoint(endpoint: str) -> str:
    """Return ``endpoint`` without userinfo or credential-looking query values.

    Total by construction: it works on the text, so a malformed endpoint (the usual reason someone
    opens the posture view) is displayed redacted instead of raising.
    """
    return redact_sensitive_text(_USERINFO.sub("[REDACTED]@", endpoint))


def is_local_trace_only() -> bool:
    """True when ``MYRM_LOCAL_TRACE_ONLY`` enforces zero remote trace egress."""
    return _env("MYRM_LOCAL_TRACE_ONLY").lower() in _TRUTHY


def is_local_endpoint(endpoint: str) -> bool:
    """True when the endpoint's parsed host is ``localhost`` or a loopback address.

    The host is parsed, not prefix-matched, so ``localhost.attacker.example`` and
    ``http://localhost@attacker.example`` are remote.
    """
    try:
        parsed = urllib.parse.urlsplit(endpoint if "://" in endpoint else f"//{endpoint}")
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def assert_local_trace_only(endpoint: str | None = None) -> None:
    """Raise PermissionError when local-trace-only mode is on and ``endpoint`` is remote."""
    if is_local_trace_only() and endpoint and not is_local_endpoint(endpoint):
        raise PermissionError(
            f"Security Policy Violation: Remote trace export to '{redact_endpoint(endpoint)}' "
            "is blocked in local-trace-only mode."
        )


def apply_local_isolation(target: OtlpTarget | None, *, requested: bool) -> OtlpTarget | None:
    """Enforce the zero-egress gate on ``target``.

    A remote target is refused with ``PermissionError`` when the operator's ``MYRM_LOCAL_TRACE_ONLY``
    policy is set, and dropped with a warning when only the caller asked for local-only export.
    """
    if target is None or is_local_endpoint(target.endpoint) or not (requested or is_local_trace_only()):
        return target
    assert_local_trace_only(target.endpoint)
    logger.warning(
        "Local-trace-only mode active: ignoring remote OTLP %s endpoint '%s'",
        target.signal,
        redact_endpoint(target.endpoint),
    )
    return None
