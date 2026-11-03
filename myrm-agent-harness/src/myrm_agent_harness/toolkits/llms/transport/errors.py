"""Transport errors raised when a provider answers a model call with a failure status.

[INPUT]
- httpx::Response (POS: the failed HTTP answer)

[OUTPUT]
- LLMHTTPError: a non-2xx answer, carrying the status, the parsed body and the response
- LLMStreamError: an error event inside an already-open stream
- LLMResponseError: a 2xx answer that is not the JSON object the wire expects
- raise_for_status / araise_for_status: turn a failed response into LLMHTTPError (sync / async, streaming-safe)

[POS]
The exception types of the model transport. Their attributes (``status_code``, ``body``, ``response``)
are the shape ``errors.normalize`` already reads from every client SDK, so the failure classifier,
retry-after reader and gateway-rejection recovery work on it without any provider-specific branch.
"""

from __future__ import annotations

import json
from typing import Final

import httpx

_MESSAGE_LIMIT = 2000

# The HTTP status a provider's error kind stands for. An error event follows the 200 status line, so the kind is all
# that tells a rejected request (never worth repeating) from a fault on the provider's side (worth repeating).
_STATUS_OF_KIND: Final = {
    "invalid_request_error": 400,
    "authentication_error": 401,
    "billing_error": 402,
    "permission_error": 403,
    "not_found_error": 404,
    "request_too_large": 413,
    "rate_limit_error": 429,
    "rate_limit_exceeded": 429,
    "api_error": 500,
    "server_error": 500,
    "internal_error": 500,
    "internal_server_error": 500,
    "timeout_error": 504,
    "overloaded_error": 529,
    "overloaded": 529,
}
# An event that names neither a status nor a known kind reports a fault after the provider accepted the request.
_UNNAMED_STATUS: Final = 500


class LLMHTTPError(Exception):
    """A provider answered with a non-2xx status."""

    def __init__(
        self,
        provider: str,
        status_code: int,
        body_text: str,
        response: httpx.Response,
    ) -> None:
        self.llm_provider = provider
        self.status_code = status_code
        self.response = response
        self.body = _parse_body(body_text)
        super().__init__(f"{provider} API error {status_code}: {body_text[:_MESSAGE_LIMIT]}")


class LLMStreamError(Exception):
    """A provider reported a failure inside an already-open stream (HTTP 200 with an error event).

    ``status_code`` is the HTTP status the event stands for: the one it carries, else the one its kind implies, else a
    server fault. The failure classifier then treats the event like the same failure answered with a status.
    """

    def __init__(self, provider: str, payload: dict[str, object]) -> None:
        self.llm_provider = provider
        self.body = payload
        self.status_code = _error_status(payload)
        super().__init__(f"{provider} stream error: {json.dumps(payload, ensure_ascii=False)[:_MESSAGE_LIMIT]}")


class LLMResponseError(ValueError):
    """A 2xx answer that is not the JSON object the wire expects (a gateway's error page, a cut-off body).

    It carries the 502 of a gateway that relayed an invalid upstream answer, so the failure classifier treats it as the
    provider fault it is and not as an unknown error nobody can act on.
    """

    status_code = 502

    def __init__(self, provider: str, message: str) -> None:
        self.llm_provider = provider
        super().__init__(message)


def _error_status(payload: dict[str, object]) -> int:
    error = payload.get("error")
    detail = error if isinstance(error, dict) else payload
    code = detail.get("code")
    if isinstance(code, int) and 400 <= code < 600:
        return code
    if isinstance(code, str) and code.isdigit() and 400 <= int(code) < 600:
        return int(code)
    for kind in (code, detail.get("type")):
        if isinstance(kind, str) and (status := _STATUS_OF_KIND.get(kind.lower())):
            return status
    return _UNNAMED_STATUS


def _parse_body(text: str) -> dict[str, object]:
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def raise_for_status(response: httpx.Response, provider: str) -> None:
    """Raise LLMHTTPError for a failed response; reads the body of a streamed one first."""
    if response.is_success:
        return
    response.read()
    raise LLMHTTPError(provider, response.status_code, response.text, response)


async def araise_for_status(response: httpx.Response, provider: str) -> None:
    """Async twin of :func:`raise_for_status`."""
    if response.is_success:
        return
    await response.aread()
    raise LLMHTTPError(provider, response.status_code, response.text, response)
