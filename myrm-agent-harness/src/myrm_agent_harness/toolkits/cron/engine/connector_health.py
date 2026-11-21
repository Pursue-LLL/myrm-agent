"""Structured connector health degradation and failure classification for cron automations.

Pure deterministic functions and data models — no I/O, safe to import anywhere in harness and server.
Used to classify outbound delivery and connector failures, to name a delivery destination without exposing
its address, and to redact credentials in target endpoints.

[INPUT]
- Exception or error message text
- Delivery channel and target address

[OUTPUT]
- ConnectorErrorCategory: Canonical failure taxonomy
- ConnectorHealthStatus: HEALTHY / DEGRADED / DOWN state machine
- classify_connector_error: Classifies raw exceptions or error strings into categories
- delivery_target_key: Stable, address-free identity of an outbound delivery destination
- redact_connector_url: Strips passwords, auth tokens, and sensitive query params from target URLs
- ConnectorFailureDetail: Structured error metadata

[POS]
Harness-level domain models and taxonomy for automation connector health diagnostics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from myrm_agent_harness.core.security.redact import redact_sensitive_text


class ConnectorErrorCategory(StrEnum):
    """Canonical classification for connector and delivery failures."""

    HTTP_CLIENT_ERROR = "http_client_error"  # 4xx errors (excluding 401/403 auth)
    HTTP_SERVER_ERROR = "http_server_error"  # 500, 502, 503, 504 gateway/upstream failures
    NETWORK_UNREACHABLE = "network_unreachable"  # DNS resolution failed, Connection Refused
    TIMEOUT = "timeout"  # Connect, read, or socket timeout
    AUTH_FAILURE = "auth_failure"  # 401 Unauthorized, 403 Forbidden, invalid key
    PAYLOAD_CONTRACT = "payload_contract"  # Invalid JSON-like response, response too large
    PROCESS_ERROR = "process_error"  # Stdio broken pipe, child process exit
    UNKNOWN = "unknown"


class ConnectorHealthStatus(StrEnum):
    """Health state of a specific connector destination."""

    HEALTHY = "healthy"  # 0 consecutive failures (or recovered)
    DEGRADED = "degraded"  # 1-2 consecutive failures, transient degradation
    DOWN = "down"  # >= 3 consecutive failures, or the latest failure was rejected credentials


# Channels whose delivery stays inside the application, so there is no external destination to monitor.
_NON_OUTBOUND_CHANNELS = frozenset({"chat", "silent", "none"})

_SENSITIVE_PARAM_NAMES = frozenset(
    {
        "access_token",
        "token",
        "secret",
        "key",
        "apikey",
        "api_key",
        "auth",
        "authorization",
        "password",
        "sig",
        "signature",
        "sign",
    }
)


def redact_connector_url(url: str | None) -> str:
    """Safely redact credentials and tokens from a connector target URL.

    - Masks basic auth password: https://user:***@host:port/path
    - Masks known sensitive query params: ?access_token=***&key=***
    - Preserves hostname, port, and safe query parameters for diagnostics.
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return redact_sensitive_text(url)

    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, hostport = netloc.split("@", 1)
        if ":" in userinfo:
            username = userinfo.split(":", 1)[0]
            netloc = f"{username}:***@{hostport}"
        else:
            netloc = f"***@{hostport}"

    query_parts: list[tuple[str, str]] = []
    if parsed.query:
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            if k.lower() in _SENSITIVE_PARAM_NAMES:
                query_parts.append((k, "***"))
            else:
                query_parts.append((k, v))
        new_query = urlencode(query_parts)
    else:
        new_query = ""

    redacted = urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
    return redacted


def delivery_target_key(channel: str, target: str | None) -> str:
    """Name an outbound delivery destination, or return an empty string when the delivery has none.

    Every job that delivers to the same channel and address gets the same key, whatever the job. The key is a digest,
    so run records that carry it never expose the address (a webhook URL holds its token, a bot hook its key).
    """
    address = (target or "").strip()
    if channel in _NON_OUTBOUND_CHANNELS or not address:
        return ""
    return hashlib.sha256(f"{channel}\0{address}".encode()).hexdigest()[:32]


def classify_connector_error(error: Exception | str | None) -> tuple[ConnectorErrorCategory, str]:
    """Classify an exception or error string into a structured category and clean message.

    An exception whose text is empty (httpx timeouts, ``asyncio.TimeoutError``) is classified by its type name.

    Returns:
        (category, human_readable_summary)
    """
    if isinstance(error, Exception):
        error_text = str(error).strip() or type(error).__name__
    else:
        error_text = error.strip() if error else "Unknown error"

    lower = error_text.lower()

    # 1. Pattern matching for HTTP status inside error text
    if (
        "webhook returned 401" in lower
        or "webhook returned 403" in lower
        or "unauthorized" in lower
        or "forbidden" in lower
    ):
        return ConnectorErrorCategory.AUTH_FAILURE, "Destination rejected credentials (401/403)"
    if "webhook returned 4" in lower:
        return ConnectorErrorCategory.HTTP_CLIENT_ERROR, "Destination rejected request (4xx)"
    if "webhook returned 502" in lower or "502 bad gateway" in lower:
        return ConnectorErrorCategory.HTTP_SERVER_ERROR, "Destination gateway down (502 Bad Gateway)"
    if "webhook returned 503" in lower or "503 service unavailable" in lower:
        return ConnectorErrorCategory.HTTP_SERVER_ERROR, "Destination service unavailable (503)"
    if "webhook returned 504" in lower or "504 gateway timeout" in lower:
        return ConnectorErrorCategory.TIMEOUT, "Destination gateway timed out (504)"
    if "webhook returned 5" in lower or "internal server error" in lower:
        return ConnectorErrorCategory.HTTP_SERVER_ERROR, "Destination internal server error (5xx)"

    # 2. Timeout patterns
    if any(k in lower for k in ("timed out", "timeout", "deadline", "readtimeout", "connecttimeout")):
        return ConnectorErrorCategory.TIMEOUT, "Connection or read timed out"

    # 3. Network and DNS resolution patterns
    if any(
        k in lower
        for k in (
            "connection refused",
            "econnrefused",
            "name or service not known",
            "nodename nor servname",
            "dns",
            "unreachable",
            "network is unreachable",
            "ssl",
            "certificate",
            "tlsv1",
            "handshake failure",
            "connection reset",
            "econnreset",
            "connection aborted",
            "all connection attempts failed",
        )
    ):
        return ConnectorErrorCategory.NETWORK_UNREACHABLE, "Destination network or DNS unreachable"

    # 4. Payload / contract patterns
    if any(k in lower for k in ("content toolarge", "invalid json", "contract error", "payload too large")):
        return ConnectorErrorCategory.PAYLOAD_CONTRACT, "Response payload or contract invalid"

    # 5. Process / stdio errors
    if any(k in lower for k in ("broken pipe", "process exited", "subprocess terminated")):
        return ConnectorErrorCategory.PROCESS_ERROR, "Connector child process exited unexpectedly"

    return ConnectorErrorCategory.UNKNOWN, error_text[:120]


@dataclass(frozen=True, slots=True)
class ConnectorFailureDetail:
    """Structured failure diagnostic metadata attached to CronRunRecord."""

    category: ConnectorErrorCategory
    target: str
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "target": self.target,
            "message": self.message,
            "timestamp": self.timestamp,
        }


__all__ = [
    "ConnectorErrorCategory",
    "ConnectorFailureDetail",
    "ConnectorHealthStatus",
    "classify_connector_error",
    "delivery_target_key",
    "redact_connector_url",
]
