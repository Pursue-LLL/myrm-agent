"""Transport errors raised when a provider answers a model call with a failure status.

[INPUT]
- httpx::Response (POS: the failed HTTP answer)

[OUTPUT]
- LLMHTTPError: a non-2xx answer, carrying the status, the parsed body and the response
- LLMAnswerError: a failure the provider reports inside a 2xx answer (an error event of an open stream, or an error body)
- LLMResponseError: a 2xx answer that is not the JSON object the wire expects
- error_status: the HTTP status a failure reported inside a 2xx answer stands for
- BASE_RESP_STATUS: the HTTP statuses of the failure codes MiniMax answers with in ``base_resp``
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
# MiniMax answers a failure with HTTP 200 and its own code in ``base_resp``; these are the HTTP statuses they stand for.
BASE_RESP_STATUS: Final = {1002: 429, 1004: 401, 1008: 402, 1026: 400, 2013: 400, 2049: 401}
# An event that names neither a status nor a known kind and interrupts a stream the provider had accepted reports a
# fault on its side.
_STREAM_UNNAMED_STATUS: Final = 500


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


class LLMAnswerError(Exception):
    """A provider reported a failure inside a 2xx answer: an error event of an open stream, or an error body.

    ``status_code`` is the HTTP status the failure stands for: the one it carries, else the one its kind implies, else
    (for an event that interrupts a stream the provider had accepted) a server fault. A body that replaces the whole
    answer and names nothing stays unknown (``None``), as the failure of a request answered with such a body always
    was, so nothing retries a request the provider may have rejected. The failure classifier then treats the
    failure like the same one answered with a status.
    """

    def __init__(self, provider: str, payload: dict[str, object], *, stream: bool = False) -> None:
        self.llm_provider = provider
        self.body = payload
        self.status_code = error_status(payload, in_stream=stream)
        where = "stream" if stream else "answer"
        super().__init__(f"{provider} {where} error: {json.dumps(payload, ensure_ascii=False)[:_MESSAGE_LIMIT]}")


class LLMResponseError(ValueError):
    """A 2xx answer that is not the JSON object the wire expects (a gateway's error page, a cut-off body).

    It carries the 502 of a gateway that relayed an invalid upstream answer, so the failure classifier treats it as the
    provider fault it is and not as an unknown error nobody can act on.
    """

    status_code = 502

    def __init__(self, provider: str, message: str) -> None:
        self.llm_provider = provider
        super().__init__(message)


def error_status(payload: dict[str, object], *, in_stream: bool) -> int | None:
    """The HTTP status a failure reported inside a 2xx answer stands for.

    ``payload`` is an error object, or an answer or event whose ``error`` field holds one. The status is the one the
    failure carries, else the one its kind implies; a failure that names neither is a fault of the provider when it
    interrupts a stream (``in_stream``) and stays unknown (``None``) when it is the whole answer.
    """
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
    return _STREAM_UNNAMED_STATUS if in_stream else None


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
