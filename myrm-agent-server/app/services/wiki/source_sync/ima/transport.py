"""HTTP transport for the Tencent ima OpenAPI: credentials, envelope unwrapping, error classification.

[INPUT]
- httpx (POS: async HTTP client)
- .errors / .models (POS: failure taxonomy, credential + JSON types)

[OUTPUT]
- ImaTransport: ``post(prefix, method, body)`` returning the unwrapped ``data`` object
- WIKI_PREFIX / NOTE_PREFIX: the two OpenAPI namespaces

[POS]
Every ima call is ``POST https://ima.qq.com/<prefix>/<method>`` with two credential headers and an HTTP 200
status envelope even for business failures, so classifying failures here keeps retry policy out of callers.
The origin is a constant: credentials can never be sent to a caller-chosen host.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from types import TracebackType

import httpx

from .errors import ImaAuthError, ImaError, ImaPermanentError, ImaRateLimitError, ImaTransientError
from .models import ImaCredentials, JsonObject

logger = logging.getLogger(__name__)

API_ORIGIN = "https://ima.qq.com"
WIKI_PREFIX = "/openapi/wiki/v1"
NOTE_PREFIX = "/openapi/note/v1"

# The envelope is documented as {retcode, errmsg, data} while live responses also use {code, msg, data};
# reading only one spelling would turn every success into "failed with code None".
_CODE_KEYS = ("retcode", "code")
_MESSAGE_KEYS = ("errmsg", "msg")
_CREDENTIAL_CODES = frozenset({20004, 200002, 110030})
_RATE_LIMIT_CODES = frozenset({20002, 110021})
_RETRYABLE_CODES = frozenset({110010, 100003})

_MAX_JSON_BYTES = 16 * 1024 * 1024
_TRANSIENT_BACKOFF_S = (1.0, 3.0)
_DEFAULT_RATE_LIMIT_PAUSE_S = 60.0
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT = "Myrm-Agent-Wiki/1.0 (ima-sync)"


def _first_int(payload: Mapping[str, object], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in payload:
            try:
                return int(str(payload[key]))
            except ValueError:
                continue
    return None


def _first_text(payload: Mapping[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value).strip()
    return ""


def unwrap_envelope(payload: object, *, status_code: int) -> JsonObject:
    """Return the envelope's ``data`` object or raise the failure its code maps to."""
    if not isinstance(payload, dict):
        raise ImaPermanentError(f"ima returned an unexpected payload (HTTP {status_code})")
    code = _first_int(payload, _CODE_KEYS)
    if code is None:
        raise ImaPermanentError(f"ima returned an unrecognized response (HTTP {status_code})")
    if code == 0:
        data = payload.get("data")
        return data if isinstance(data, dict) else {}
    message = _first_text(payload, _MESSAGE_KEYS)
    if code in _CREDENTIAL_CODES:
        raise ImaAuthError(message or f"ima rejected the credentials (code {code})")
    if code in _RATE_LIMIT_CODES:
        raise ImaRateLimitError(message or "ima rate limit reached", retry_after_s=_DEFAULT_RATE_LIMIT_PAUSE_S)
    if code in _RETRYABLE_CODES:
        raise ImaTransientError(message or f"ima is temporarily unavailable (code {code})")
    raise ImaPermanentError(message or f"ima request failed with code {code}")


def _classify_response(response: httpx.Response) -> JsonObject:
    status = response.status_code
    if status in {401, 403}:
        raise ImaAuthError(f"ima rejected the credentials (HTTP {status})")
    if status == 429:
        retry_after = response.headers.get("retry-after", "")
        pause = float(retry_after) if retry_after.isdigit() else _DEFAULT_RATE_LIMIT_PAUSE_S
        raise ImaRateLimitError("ima rate limit reached", retry_after_s=pause)
    if status >= 500 or status == 408:
        raise ImaTransientError(f"ima server error (HTTP {status})")
    if not response.is_success:
        raise ImaPermanentError(f"ima rejected the request (HTTP {status})")
    if len(response.content) > _MAX_JSON_BYTES:
        raise ImaPermanentError("ima response exceeds the size limit")
    try:
        payload: object = response.json()
    except ValueError:
        payload = None
    return unwrap_envelope(payload, status_code=status)


class ImaTransport:
    """Owns one connection pool; use as ``async with`` so it is always closed."""

    def __init__(
        self,
        credentials: ImaCredentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_ORIGIN,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
                "ima-openapi-clientid": credentials.client_id,
                "ima-openapi-apikey": credentials.api_key,
            },
            timeout=_TIMEOUT,
            transport=transport,
        )

    async def __aenter__(self) -> ImaTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def post(self, prefix: str, method: str, body: JsonObject) -> JsonObject:
        """POST one method; transient failures are retried here, everything else surfaces to the caller."""
        last_error: ImaError = ImaTransientError("ima request failed")
        for attempt in range(len(_TRANSIENT_BACKOFF_S) + 1):
            try:
                response = await self._client.post(f"{prefix}/{method}", json=body)
                return _classify_response(response)
            except httpx.TransportError as exc:
                last_error = ImaTransientError(f"ima network failure: {type(exc).__name__}")
            except ImaTransientError as exc:
                last_error = exc
            if attempt < len(_TRANSIENT_BACKOFF_S):
                await asyncio.sleep(_TRANSIENT_BACKOFF_S[attempt])
        logger.info("ima %s/%s failed after retries: %s", prefix, method, last_error)
        raise last_error
