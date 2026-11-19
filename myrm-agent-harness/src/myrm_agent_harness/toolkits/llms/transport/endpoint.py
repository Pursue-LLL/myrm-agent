"""Endpoint grammar: what an address a user typed or pasted means to the model transport.

[INPUT]
- urllib.parse (POS: splitting and joining a URL)

[OUTPUT]
- Endpoint / NO_QUERY: the root a wire appends its own path to, and the query that rides with every request to it
- parse_endpoint: the generic grammar, for callers that name their own operation suffixes (embeddings, rerank, images)
- parse_wire_endpoint: the grammar of one chat wire (Azure, Gemini, Anthropic, Ollama, Bedrock, OpenAI-compatible)
- InvalidEndpointError: the text is not an absolute http(s) URL
- GEMINI_OFFICIAL_HOST: Google's own API host

[POS]
The single owner of address grammar. People paste a root (``https://gw.example/v1``), a full operation URL
(``.../v1/chat/completions``), the Azure portal's *Target URI* (``.../openai/deployments/x/chat/completions?api-version=...``)
or an OpenAI-compatibility base; every one reduces here to a root plus a query, so the UI, the connectivity check and
the request builders never carry a grammar of their own. A query is a client's ``default_query`` (the OpenAI SDK's term):
it belongs to the endpoint, not to the path, and a fragment never reaches a server. Credentials in the authority are left
alone: the HTTP client turns them into a Basic header, which is what the user asked for.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from urllib.parse import SplitResult, parse_qsl, urlsplit, urlunsplit

GEMINI_OFFICIAL_HOST: Final = "generativelanguage.googleapis.com"

# Operations a pasted address may end with, longest first: ``/chat/completions`` also ends with ``/completions``.
# ``/models`` is the model list of a provider whose chat route sits beside it (DeepSeek serves ``GET /models``).
_OPERATIONS: Final = ("/chat/completions", "/completions", "/embeddings", "/models", "/responses")
_ANTHROPIC_OPERATIONS: Final = ("/v1/messages", "/messages", "/v1")
_OLLAMA_OPERATIONS: Final = ("/api/chat", "/api/generate", "/api", "/v1")
# Azure addresses a resource at ``/openai`` (a deployment under ``/openai/deployments/{name}``, the v1 route under
# ``/openai/v1``); the transport adds that part itself, so an address that already holds it would double it.
_AZURE_RESOURCE_PATH: Final = re.compile(r"/openai(?:/v1|/deployments/[^/]+)?$")
# Google's OpenAI-compatibility base (``/v1beta/openai``) does not route the native ``:generateContent`` calls.
_GEMINI_COMPATIBILITY_BASE: Final = re.compile(r"(/v\d+(?:alpha|beta)?)/openai$")
NO_QUERY: Final[Mapping[str, str]] = MappingProxyType({})


class InvalidEndpointError(ValueError):
    """The text is not an absolute http(s) URL."""


@dataclass(frozen=True, slots=True)
class Endpoint:
    """An address reduced to what a request is built on."""

    root: str
    query: Mapping[str, str] = NO_QUERY


def _split(raw: str) -> SplitResult:
    """``raw`` as a URL; the message omits it, since an address may carry a key."""
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        parts = None
    if parts is None or parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidEndpointError("The endpoint must be an absolute http:// or https:// URL")
    return parts


def _strip_tail(path: str, tails: Sequence[str]) -> str:
    """``path`` without the first of ``tails`` it ends with."""
    for tail in tails:
        if path.endswith(tail):
            return path[: -len(tail)]
    return path


def _endpoint(parts: SplitResult, path: str) -> Endpoint:
    query = MappingProxyType(dict(parse_qsl(parts.query, keep_blank_values=True)))
    return Endpoint(urlunsplit((parts.scheme, parts.netloc, path, "", "")), query)


def parse_endpoint(raw: str, operations: Sequence[str]) -> Endpoint:
    """``raw`` reduced to its root and query, an address ending in one of ``operations`` cut back to the root."""
    parts = _split(raw)
    return _endpoint(parts, _strip_tail(parts.path.rstrip("/"), operations))


def _gemini_path(path: str, host: str) -> str:
    """The native root: ``models/{id}:generateContent`` and the OpenAI-compatibility base are not part of it."""
    head, separator, _ = path.rpartition("/models/")
    path = _GEMINI_COMPATIBILITY_BASE.sub(r"\1", head if separator else path)
    # Google's host named without its API version; a relay's host is not assumed to share Google's layout.
    return path if path or host != GEMINI_OFFICIAL_HOST else "/v1beta"


def parse_wire_endpoint(raw: str, wire: str, api_path: str) -> Endpoint:
    """``raw`` reduced to the root ``wire`` appends its own path to.

    ``api_path`` is the path the provider's API lives under: an address that stops short of it (a bare host, a gateway
    prefix) gets it appended, so ``https://gw.example`` and ``https://gw.example/v1`` reach the same API.
    """
    parts = _split(raw)
    path = _strip_tail(parts.path.rstrip("/"), _OPERATIONS)
    if wire == "azure_openai":
        path = _AZURE_RESOURCE_PATH.sub("", path)
    if wire in ("openai_chat", "azure_openai"):
        path = path if path.endswith(api_path) else path + api_path
    elif wire == "anthropic":
        path = _strip_tail(path, _ANTHROPIC_OPERATIONS)
    elif wire == "ollama":
        path = _strip_tail(path, _OLLAMA_OPERATIONS)
    elif wire == "bedrock":  # a pasted operation URL (``.../model/{id}/converse``) is cut back to the root
        path = path.partition("/model/")[0]
    elif wire == "gemini":
        path = _gemini_path(path, parts.hostname or "")
    return _endpoint(parts, path)
