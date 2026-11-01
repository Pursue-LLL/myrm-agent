"""Model transport: typed protocol wires over httpx for every LLM provider.

[INPUT]
- transport.client (POS: LLMTransport facade)
- transport.errors (POS: LLMHTTPError / LLMStreamError)
- transport.profile (POS: provider table and route resolution)

[OUTPUT]
- LLMTransport / get_transport: chat and Responses calls against any supported provider
- LLMHTTPError / LLMStreamError: the failures a call can raise
- Route / UnsupportedProviderError / resolve_route / speaks_openai_body / PROFILES: provider resolution

[POS]
Replaces the third-party multi-provider client library. Five wires (OpenAI chat, OpenAI Responses, Anthropic
Messages, Gemini generateContent, Ollama chat) cover every provider; a provider that speaks the OpenAI protocol is a
data row in ``profile.PROFILES``. Imports stay light: no provider SDK is loaded.
"""

from myrm_agent_harness.toolkits.llms.transport.client import LLMTransport, get_transport
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError, LLMStreamError
from myrm_agent_harness.toolkits.llms.transport.profile import (
    PROFILES,
    Route,
    UnsupportedProviderError,
    resolve_route,
    speaks_openai_body,
)

__all__ = [
    "PROFILES",
    "LLMHTTPError",
    "LLMStreamError",
    "LLMTransport",
    "Route",
    "UnsupportedProviderError",
    "get_transport",
    "resolve_route",
    "speaks_openai_body",
]
