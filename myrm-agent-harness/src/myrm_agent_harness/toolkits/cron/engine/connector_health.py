"""Failure classification and destination identity for cron result deliveries.

Pure deterministic functions and data models — no I/O, safe to import anywhere in harness and server.
Used to classify a failed delivery, to name a delivery destination without exposing its address, and to mask the
credentials a target address carries.

[INPUT]
- Exception or error message text
- Delivery channel and target address

[OUTPUT]
- ConnectorErrorCategory: Canonical failure taxonomy
- classify_connector_error: Classifies raw exceptions or error strings into categories
- delivery_target_key: Stable, address-free identity of a delivery destination
- redact_connector_url: Masks the basic-auth password and sensitive query parameters of a target address
- ConnectorFailureDetail: The category and masked address stored beside a failed delivery's run record

[POS]
Harness-level failure taxonomy and destination identity for cron delivery diagnostics. Judging a destination's
health from its failures is the application's rule, not this module's.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from myrm_agent_harness.core.security.redact import redact_sensitive_text


class ConnectorErrorCategory(StrEnum):
    """Canonical classification for connector and delivery failures."""

    HTTP_CLIENT_ERROR = "http_client_error"  # 4xx (not 401/403), a bot hook's business-code rejection, redirect loop
    HTTP_SERVER_ERROR = "http_server_error"  # 500, 502, 503 gateway/upstream failures
    NETWORK_UNREACHABLE = "network_unreachable"  # DNS failed, connection refused/reset/closed, TLS failure
    TIMEOUT = "timeout"  # Connect, read, or socket timeout, 504
    AUTH_FAILURE = "auth_failure"  # 401 Unauthorized, 403 Forbidden, invalid key
    PAYLOAD_CONTRACT = "payload_contract"  # Response is not HTTP or not valid JSON, response too large
    ADDRESS_REJECTED = "address_rejected"  # The address cannot be dialed: unsupported scheme, malformed, internal host
    UNKNOWN = "unknown"


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
    """Mask the credentials a target address carries in its userinfo and its query string.

    - Basic-auth password: https://user:***@host:port/path
    - Query parameters with a sensitive name: ?access_token=***&key=***
    - Host, port, path and the other query parameters stay as written. A secret that sits in the path (the token of
      a Feishu, Slack or Discord hook) is not masked, so the result for an address like that is not safe to show.
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
    """Name a delivery destination, or return an empty string when the delivery has no address.

    Every job that delivers to the same channel and address gets the same key, whatever the job. The key is a digest,
    so run records that carry it never expose the address (a webhook URL holds its token, a bot hook its key). Which
    channels send outside the application is the application's rule, not this function's.
    """
    address = (target or "").strip()
    if not address:
        return ""
    return hashlib.sha256(f"{channel}\0{address}".encode()).hexdigest()[:32]


# Lowercase fragments of the error texts the delivery code paths raise.
# A refusal that carries no 4xx status: a bot hook's error code in a 200 reply (Feishu `code`, WeCom `errcode`), a
# redirect loop.
_REFUSAL_MARKERS = ("bot webhook error code", "bot webhook errcode", "too many redirects")
_ADDRESS_REJECTED_MARKERS = (
    "blocked url scheme",
    "blocked hostname",
    "missing hostname",
    "malformed url",
    "invalid hostname",
    "invalid port",
    "hostname contains percent-encoding",
    "parser-confusing characters",
    "internal network is blocked",
)
_PAYLOAD_MARKERS = (
    "content too large",
    "body too large",
    "payload too large",
    "invalid json",
    "contract error",
    "illegal status line",
)
_TIMEOUT_MARKERS = ("timed out", "timeout", "deadline")
_NETWORK_MARKERS = (
    "connection refused",
    "econnrefused",
    "name or service not known",
    "nodename nor servname",
    "dns",
    "unreachable",
    "ssl",
    "certificate",
    "tlsv1",
    "handshake failure",
    "connection reset",
    "econnreset",
    "connection aborted",
    "all connection attempts failed",
    "broken pipe",
    "server disconnected",
    "peer closed connection",
)
# An httpx error that carries no text reaches the classifier as its type name.
_NETWORK_ERROR_TYPE = re.compile(r"\b(?:read|write|connect)error\b")


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def classify_connector_error(error: Exception | str | None) -> tuple[ConnectorErrorCategory, str]:
    """Classify an exception or error string into a structured category and clean message.

    An exception whose text is empty (httpx timeouts and read/write/connect errors, ``asyncio.TimeoutError``) is
    classified by its type name.

    Returns:
        (category, human_readable_summary)
    """
    if isinstance(error, Exception):
        error_text = str(error).strip() or type(error).__name__
    else:
        error_text = error.strip() if error else "Unknown error"

    lower = error_text.lower()

    # 1. HTTP status inside error text; a refusal without a 4xx status is classed with the 4xx
    if (
        "webhook returned 401" in lower
        or "webhook returned 403" in lower
        or "unauthorized" in lower
        or "forbidden" in lower
    ):
        return ConnectorErrorCategory.AUTH_FAILURE, "Destination rejected credentials (401/403)"
    if "webhook returned 4" in lower:
        return ConnectorErrorCategory.HTTP_CLIENT_ERROR, "Destination rejected request (4xx)"
    if _has_any(lower, _REFUSAL_MARKERS):
        return ConnectorErrorCategory.HTTP_CLIENT_ERROR, "Destination refused request (no 4xx status)"
    if "webhook returned 502" in lower or "502 bad gateway" in lower:
        return ConnectorErrorCategory.HTTP_SERVER_ERROR, "Destination gateway down (502 Bad Gateway)"
    if "webhook returned 503" in lower or "503 service unavailable" in lower:
        return ConnectorErrorCategory.HTTP_SERVER_ERROR, "Destination service unavailable (503)"
    if "webhook returned 504" in lower or "504 gateway timeout" in lower:
        return ConnectorErrorCategory.TIMEOUT, "Destination gateway timed out (504)"
    if "webhook returned 5" in lower or "internal server error" in lower:
        return ConnectorErrorCategory.HTTP_SERVER_ERROR, "Destination internal server error (5xx)"

    # 2. The address was refused before any request went out
    if _has_any(lower, _ADDRESS_REJECTED_MARKERS):
        return ConnectorErrorCategory.ADDRESS_REJECTED, "Destination address cannot be used"

    # 3. A reply that is not what a webhook answers with. Checked ahead of the generic network words below, which
    #    can occur in the bytes an illegal status line echoes back.
    if _has_any(lower, _PAYLOAD_MARKERS):
        return ConnectorErrorCategory.PAYLOAD_CONTRACT, "Response payload or contract invalid"

    # 4. Timeouts
    if _has_any(lower, _TIMEOUT_MARKERS):
        return ConnectorErrorCategory.TIMEOUT, "Connection or read timed out"

    # 5. Network, DNS and TLS failures
    if _has_any(lower, _NETWORK_MARKERS) or _NETWORK_ERROR_TYPE.search(lower):
        return ConnectorErrorCategory.NETWORK_UNREACHABLE, "Destination network or DNS unreachable"

    return ConnectorErrorCategory.UNKNOWN, error_text[:120]


@dataclass(frozen=True, slots=True)
class ConnectorFailureDetail:
    """What a failed delivery's run record keeps about the failure: its category and the masked address."""

    category: ConnectorErrorCategory
    target: str

    def to_dict(self) -> dict[str, object]:
        return {"category": self.category.value, "target": self.target}


__all__ = [
    "ConnectorErrorCategory",
    "ConnectorFailureDetail",
    "classify_connector_error",
    "delivery_target_key",
    "redact_connector_url",
]
