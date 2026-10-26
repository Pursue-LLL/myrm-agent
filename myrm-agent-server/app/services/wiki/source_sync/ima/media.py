"""Bounded, host-allowlisted download of an ima media file.

[INPUT]
- httpx (POS: async HTTP client)
- .errors (POS: failure taxonomy)

[OUTPUT]
- download_media: stream a signed COS URL into memory under a hard byte cap
- MAX_DOWNLOAD_BYTES

[POS]
The download URL arrives inside an API response, so it is untrusted input: https only, Tencent COS or ima's
own resource host only, no redirects, ima credentials never attached, and the size is capped both by the
advertised length and while streaming.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .errors import ImaPermanentError, ImaTooLargeError, ImaTransientError

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024

_TRUSTED_ROOT_DOMAINS = ("myqcloud.com",)
_TRUSTED_HOSTS = frozenset({"res-pkb.ima.qq.com"})
# Hop-by-hop and identity headers are never forwarded, whatever the API response suggests.
_FORBIDDEN_HEADERS = frozenset({"connection", "content-length", "cookie", "host", "proxy-authorization", "transfer-encoding"})
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_GONE_STATUSES = frozenset({404, 410})


def validate_media_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ImaPermanentError("ima media URL must use https")
    trusted = host in _TRUSTED_HOSTS or any(host == root or host.endswith(f".{root}") for root in _TRUSTED_ROOT_DOMAINS)
    if not trusted:
        raise ImaPermanentError("ima media URL is outside the trusted Tencent hosts")


def _forwardable(headers: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() not in _FORBIDDEN_HEADERS}


async def download_media(
    url: str,
    headers: dict[str, str],
    *,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Return the file bytes; a 404/410 is permanent, other HTTP and network failures are retryable."""
    validate_media_url(url)
    try:
        async with (
            httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False, transport=transport) as client,
            client.stream("GET", url, headers=_forwardable(headers)) as response,
        ):
            if response.status_code in _GONE_STATUSES:
                raise ImaPermanentError(f"ima media is gone (HTTP {response.status_code})")
            if not response.is_success:
                raise ImaTransientError(f"ima media download failed (HTTP {response.status_code})")
            length = response.headers.get("content-length", "")
            if length.isdigit() and int(length) > max_bytes:
                raise ImaTooLargeError(f"ima media exceeds {max_bytes} bytes")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ImaTooLargeError(f"ima media exceeds {max_bytes} bytes")
            return bytes(body)
    except httpx.TransportError as exc:
        raise ImaTransientError(f"ima media download failed: {type(exc).__name__}") from exc
