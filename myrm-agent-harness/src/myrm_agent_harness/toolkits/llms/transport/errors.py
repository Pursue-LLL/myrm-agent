"""Transport errors raised when a provider answers a model call with a failure status.

[INPUT]
- httpx::Response (POS: the failed HTTP answer)

[OUTPUT]
- LLMHTTPError: a non-2xx answer, carrying the status, the parsed body and the response
- LLMStreamError: an error event inside an already-open stream
- raise_for_status / araise_for_status: turn a failed response into LLMHTTPError (sync / async, streaming-safe)

[POS]
The one exception type of the model transport. Its attributes (``status_code``, ``body``, ``response``)
are the shape ``errors.normalize`` already reads from every client SDK, so the failure classifier,
retry-after reader and gateway-rejection recovery work on it without any provider-specific branch.
"""

from __future__ import annotations

import json

import httpx

_MESSAGE_LIMIT = 2000


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
    """A provider reported a failure inside an already-open stream (HTTP 200 with an error event)."""

    def __init__(self, provider: str, payload: dict[str, object]) -> None:
        self.llm_provider = provider
        self.body = payload
        self.status_code = _error_status(payload)
        super().__init__(f"{provider} stream error: {json.dumps(payload, ensure_ascii=False)[:_MESSAGE_LIMIT]}")


def _error_status(payload: dict[str, object]) -> int | None:
    error = payload.get("error")
    code = error.get("code") if isinstance(error, dict) else payload.get("code")
    if isinstance(code, int) and 400 <= code < 600:
        return code
    if isinstance(code, str) and code.isdigit() and 400 <= int(code) < 600:
        return int(code)
    return None


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
