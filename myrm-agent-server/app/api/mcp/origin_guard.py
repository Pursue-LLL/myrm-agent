"""DNS-rebinding and origin validation guard for the HTTP MCP transport.

[INPUT]
- starlette.types::ASGIApp, Scope, Receive, Send
- starlette.requests::Request
- starlette.responses::JSONResponse

[OUTPUT]
- McpOriginValidationMiddleware: ASGI middleware validating Origin & Host headers
- validate_mcp_request_origin: standalone helper function

[POS]
Protects local Streamable HTTP / SSE MCP endpoints from DNS-rebinding attacks
initiated by browser JavaScript.

Threat Model:
Binding to localhost / loopback interfaces keeps remote network attackers out,
but does not protect against a malicious web page opened in the user's browser.
An attacker-controlled website (e.g. `attacker.example`) can dynamically resolve
to `127.0.0.1` after page load (DNS rebinding). Under standard Same-Origin Policy,
the browser treats `http://attacker.example:8080` as same-origin and permits
attacker scripts to read responses from local services.

Defense:
Browsers always send immutable `Origin` and `Host` headers that page JavaScript
cannot strip or forge. Legitimate local tools (Cursor, Claude Code, CLI, SDKs)
omit `Origin`. This guard enforces that:
  1. Requests without `Origin` are allowed (non-browser clients).
  2. Requests with `Origin` must match loopback hostnames or explicit allowlist.
  3. Concrete interface binds enforce that `Host` matches loopback or allowlist.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Wildcard bind addresses where the incoming Host header cannot be statically known
_WILDCARD_BIND_HOSTS: frozenset[str] = frozenset({"", "0.0.0.0", "::", "[::]", "*"})

# Regex matching IPv4 loopback network 127.0.0.0/8
_IPV4_LOOPBACK_RE = re.compile(r"^127(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$")

# Permitted URI schemes for Origin headers (including desktop app & editor webview schemes)
_ALLOWED_ORIGIN_SCHEMES: frozenset[str] = frozenset({"http", "https", "tauri", "vscode-webview"})


def is_loopback_hostname(hostname: str) -> bool:
    """Determine whether a hostname strictly resolves to the loopback interface.

    0.0.0.0 is deliberately excluded because Chromium on Linux/macOS routes it
    to loopback, creating a rebinding-free attack vector from untrusted origins.
    """
    h = hostname.strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]

    if h == "localhost" or h.endswith(".localhost"):
        return True
    if h in ("127.0.0.1", "::1", "0:0:0:0:0:0:0:1"):
        return True

    # Handle IPv4-mapped IPv6 (::ffff:127.0.0.1) and standard 127.0.0.0/8 range
    v4 = h[7:] if h.startswith("::ffff:") else h
    if bool(_IPV4_LOOPBACK_RE.match(v4)):
        return True

    # Fallback to standard library IP loopback detection for heterogenous IPv6 formats
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_loopback
    except ValueError:
        return False


def normalize_origin(origin: str) -> str | None:
    """Normalize an Origin string to lowercase scheme://host[:port]."""
    raw = origin.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        if parts.scheme not in _ALLOWED_ORIGIN_SCHEMES or not parts.netloc:
            return None
        return f"{parts.scheme}://{parts.netloc.lower()}"
    except Exception:
        return None


def origin_hostname(origin: str) -> str | None:
    """Extract the hostname portion from an Origin header string."""
    raw = origin.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        if parts.scheme not in _ALLOWED_ORIGIN_SCHEMES or not parts.hostname:
            return None
        return parts.hostname.lower()
    except Exception:
        return None


def host_header_hostname(host: str) -> str | None:
    """Extract the hostname portion from a Host header (stripping optional port)."""
    raw = host.strip()
    if not raw:
        return None
    try:
        # Wrap in dummy scheme to leverage robust RFC urlsplit parsing
        parts = urlsplit(f"http://{raw}")
        return parts.hostname.lower() if parts.hostname else None
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class OriginGuard:
    """Security configuration for HTTP MCP Origin and Host validation."""

    disabled: bool
    allowed_origins: frozenset[str]
    allowed_hosts: frozenset[str]
    enforce_host: bool


def _split_env_list(val: str | None) -> list[str]:
    """Split comma-separated values from environment variables."""
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


def resolve_origin_guard(
    *,
    host: str = "127.0.0.1",
    allowed_origins: Sequence[str] | None = None,
    allowed_hosts: Sequence[str] | None = None,
) -> OriginGuard:
    """Construct an OriginGuard for an HTTP server bound to the specified host."""
    raw_origins = list(allowed_origins) if allowed_origins is not None else _split_env_list(
        os.getenv("MYRM_MCP_ALLOWED_ORIGINS")
    )
    raw_hosts = list(allowed_hosts) if allowed_hosts is not None else _split_env_list(
        os.getenv("MYRM_MCP_ALLOWED_HOSTS")
    )

    if "*" in raw_origins:
        return OriginGuard(
            disabled=True,
            allowed_origins=frozenset(),
            allowed_hosts=frozenset(),
            enforce_host=False,
        )

    norm_origins: set[str] = set()
    for o in raw_origins:
        norm = normalize_origin(o)
        if norm:
            norm_origins.add(norm)

    norm_hosts: set[str] = {h.strip().lower() for h in raw_hosts if h.strip()}

    bind_host = host.strip().lower()
    is_wildcard = bind_host in _WILDCARD_BIND_HOSTS
    if not is_wildcard and not is_loopback_hostname(bind_host):
        # Concrete non-loopback interface (e.g. 192.168.1.100) is a valid Host
        norm_hosts.add(bind_host)

    return OriginGuard(
        disabled=False,
        allowed_origins=frozenset(norm_origins),
        allowed_hosts=frozenset(norm_hosts),
        enforce_host=(not is_wildcard) or (len(norm_hosts) > 0),
    )


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """Result of origin and host security evaluation."""

    ok: bool
    reason: str = ""


def check_request_origin(
    headers: Mapping[str, str],
    guard: OriginGuard,
) -> GuardVerdict:
    """Validate request Origin and Host headers against the OriginGuard.

    Absence of an Origin header is permitted because non-browser clients
    (CLI, Cursor, Claude Code, native SDKs) omit it while browsers cannot.
    """
    if guard.disabled:
        return GuardVerdict(ok=True)

    origin = headers.get("origin")
    if origin is not None and origin.strip():
        origin_val = origin.strip()
        hostname = origin_hostname(origin_val)
        normalized = normalize_origin(origin_val)

        is_allowed = (
            (hostname is not None and is_loopback_hostname(hostname))
            or (normalized is not None and normalized in guard.allowed_origins)
        )
        if not is_allowed:
            return GuardVerdict(ok=False, reason=f"Origin not allowed: {origin_val}")

    host = headers.get("host")
    if guard.enforce_host and host is not None and host.strip():
        host_val = host.strip()
        lowered_host = host_val.lower()
        hostname = host_header_hostname(host_val)

        is_allowed = (
            (hostname is not None and is_loopback_hostname(hostname))
            or (lowered_host in guard.allowed_hosts)
            or (hostname is not None and hostname in guard.allowed_hosts)
        )
        if not is_allowed:
            return GuardVerdict(ok=False, reason=f"Host not allowed: {host_val}")

    return GuardVerdict(ok=True)


class _MCPOriginGuardMiddleware:
    """ASGI middleware enforcing DNS-rebinding protection on MCP routes."""

    def __init__(self, app: ASGIApp, guard: OriginGuard | None = None) -> None:
        self.app = app
        self.guard = guard or resolve_origin_guard()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        verdict = check_request_origin(request.headers, self.guard)
        if not verdict.ok:
            remote_addr = request.client.host if request.client else "unknown"
            logger.warning(
                "MCP request rejected by origin guard: %s (remote=%s)",
                verdict.reason,
                remote_addr,
            )
            response = JSONResponse(
                {"error": f"Forbidden: {verdict.reason}"},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
