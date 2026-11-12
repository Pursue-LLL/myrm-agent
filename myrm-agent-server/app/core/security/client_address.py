"""The client address that per-client limits and IP lists key on.

[INPUT]
- starlette.requests::HTTPConnection (POS: the HTTP or WebSocket connection whose ``client`` the ASGI server resolved)

[OUTPUT]
- UNKNOWN_CLIENT_IP: the key used when the transport reports no peer
- client_ip: the connection's client address

[POS]
Single source of the client address for rate limits, lockouts and IP lists. ``X-Forwarded-For`` and ``X-Real-IP`` are
text the visitor writes, so no application code reads them. uvicorn applies ``X-Forwarded-For`` itself, only when the
TCP peer is listed in ``FORWARDED_ALLOW_IPS`` (default ``127.0.0.1``; never ``*``), and then rewrites ``client`` to the
last hop those proxies did not add. Reading ``client`` therefore honours a configured proxy and ignores a forged header
with the same call. Behind a proxy that is not listed, every visitor shares the proxy's address, which keeps a limit
strict instead of bypassable.
"""

from __future__ import annotations

from typing import Final

from starlette.requests import HTTPConnection

UNKNOWN_CLIENT_IP: Final[str] = "unknown"


def client_ip(connection: HTTPConnection) -> str:
    """Return the connection's peer address, or ``UNKNOWN_CLIENT_IP`` when the transport reports none."""
    client = connection.client
    return client.host if client and client.host else UNKNOWN_CLIENT_IP
