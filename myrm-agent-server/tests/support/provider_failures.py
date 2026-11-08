"""A provider's error answer as the model transport raises it.

[OUTPUT]
- provider_failure(status, message): the LLMHTTPError a non-2xx answer with an OpenAI-style error body becomes

[POS]
Tests of the server's failure classifiers raise this instead of a look-alike class, so a classifier is judged on the
type and the attributes the transport really gives it.
"""

from __future__ import annotations

import json

import httpx
from myrm_agent_harness.toolkits.llms.transport import LLMHTTPError


def provider_failure(status: int, message: str, *, path: str = "/v1/chat/completions") -> LLMHTTPError:
    """The failure of a call the provider answered with ``status`` and an error body carrying ``message``."""
    body = json.dumps({"error": {"message": message}})
    request = httpx.Request("POST", f"https://provider.test{path}")
    return LLMHTTPError("openai", status, body, httpx.Response(status, content=body.encode(), request=request))
