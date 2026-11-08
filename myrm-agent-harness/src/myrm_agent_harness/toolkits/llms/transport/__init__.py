"""Model transport: typed protocol wires over httpx for every LLM provider.

[INPUT]
- transport.client (POS: LLMTransport facade)
- transport.errors (POS: LLMCallError / LLMHTTPError / LLMAnswerError)
- transport.http (POS: shared HTTP clients)
- transport.profile (POS: provider table and route resolution)

[OUTPUT]
- LLMTransport / get_transport: chat and Responses calls against any supported provider
- aclose_clients / retire_clients: close, or only forget, the shared HTTP clients (shutdown; a TLS policy that changed
  in a running process)
- LLMCallError: the base of the failures a call can raise; LLMHTTPError / LLMAnswerError: the two a caller reads the
  status and body of
- Route / UnsupportedProviderError / resolve_route / speaks_openai_body / PROFILES: provider resolution

[POS]
Six wires (OpenAI chat, OpenAI Responses, Anthropic Messages, Gemini generateContent, Ollama chat, AWS Bedrock
Converse) cover every provider; a provider that speaks the OpenAI protocol is a data row in ``profile.PROFILES``.
Imports stay light: no provider SDK is loaded, and the names resolve on first use, so reading an error class or a
provider route (the failure classifier, the HTTP server's import path) does not load the wires.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms.transport.client import LLMTransport, get_transport
    from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError, LLMCallError, LLMHTTPError
    from myrm_agent_harness.toolkits.llms.transport.http import aclose_clients, retire_clients
    from myrm_agent_harness.toolkits.llms.transport.profile import (
        PROFILES,
        Route,
        UnsupportedProviderError,
        resolve_route,
        speaks_openai_body,
    )

_EXPORT_MODULES = {
    "LLMTransport": "client",
    "get_transport": "client",
    "LLMCallError": "errors",
    "LLMHTTPError": "errors",
    "LLMAnswerError": "errors",
    "aclose_clients": "http",
    "retire_clients": "http",
    "PROFILES": "profile",
    "Route": "profile",
    "UnsupportedProviderError": "profile",
    "resolve_route": "profile",
    "speaks_openai_body": "profile",
}

__all__ = [
    "PROFILES",
    "LLMCallError",
    "LLMHTTPError",
    "LLMAnswerError",
    "LLMTransport",
    "Route",
    "UnsupportedProviderError",
    "aclose_clients",
    "get_transport",
    "resolve_route",
    "retire_clients",
    "speaks_openai_body",
]


def __getattr__(name: str) -> object:
    """Load an exported name from its module on first access."""
    module = _EXPORT_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{module}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return __all__
