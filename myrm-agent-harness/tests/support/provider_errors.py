"""Provider failures as the model transport raises them, for tests of error reading and classification.

[INPUT]
- transport.errors::LLMHTTPError (POS: the exception a failed provider answer becomes)
- httpx::Response (POS: the carrier of the status, headers and body)

[OUTPUT]
- provider_error: an ``LLMHTTPError`` for a status, a body (JSON object or plain text) and optional headers

[POS]
Tests that read or classify failures build the exception the transport really raises, so a change in what the
transport puts on it (status, parsed body, response headers) fails them instead of a hand-made look-alike passing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import httpx

from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError

_URL = "https://provider.test/v1/chat/completions"


def provider_error(
    provider: str,
    status: int,
    body: Mapping[str, object] | str,
    *,
    headers: Mapping[str, str] | None = None,
) -> LLMHTTPError:
    """The transport's failure for ``provider`` answering ``status`` with ``body`` (a JSON object or plain text)."""
    text = body if isinstance(body, str) else json.dumps(body)
    response = httpx.Response(
        status,
        content=text.encode("utf-8"),
        headers=dict(headers or {}),
        request=httpx.Request("POST", _URL),
    )
    return LLMHTTPError(provider, status, text, response)
