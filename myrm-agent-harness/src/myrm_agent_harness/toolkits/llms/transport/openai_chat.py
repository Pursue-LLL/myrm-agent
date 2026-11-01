"""OpenAI Chat Completions wire: request building, response and stream decoding.

[INPUT]
- transport.profile (POS: Route / ProviderProfile — endpoint, credential and per-provider body quirks)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest, StreamDecoder)

[OUTPUT]
- prepare: a PreparedRequest for ``/chat/completions`` (OpenAI, Azure OpenAI and every OpenAI-compatible provider)
- parse: the provider's JSON answer as the chat.completion dict the adapter consumes
- decoder: the SSE decoder yielding chat.completion.chunk dicts
- openai_endpoint: URL, query and auth headers for an OpenAI-family path (shared with the Responses wire)

[POS]
The wire most providers speak. The adapter's messages and parameters are already OpenAI-shaped, so building is
a few deterministic rules: provider body defaults, the reasoning-model parameter names, text-content flattening
for APIs that reject content arrays, and ``extra_body`` laid over the typed fields. Responses are returned as the
provider sent them, with one correction: cache reads a provider reports at the top level of ``usage`` (DeepSeek's
``prompt_cache_hit_tokens``, Anthropic-style ``cache_read_input_tokens`` from gateways) are also reported where every
usage reader looks for them (``prompt_tokens_details.cached_tokens``). The adapter reads the dict directly, so nothing
is re-parsed into SDK models.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from myrm_agent_harness.toolkits.llms.transport.errors import LLMStreamError
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, PreparedRequest, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.params import CallOptions, merge_headers, split_params
from myrm_agent_harness.toolkits.llms.transport.profile import ProviderProfile, Route, UnsupportedProviderError

logger = logging.getLogger(__name__)

_DEFAULT_AZURE_API_VERSION = "2024-10-21"
_DEFAULT_AZURE_RESPONSES_API_VERSION = "preview"
_OFFICIAL_HOST = "api.openai.com"
_TOP_LEVEL_CACHE_READ_KEYS = ("prompt_cache_hit_tokens", "cache_read_input_tokens")


def _flatten_text(messages: Sequence[Mapping[str, object]], mode: str) -> list[dict[str, object]]:
    """Turn ``content`` arrays into plain strings for APIs that reject arrays (text parts concatenated)."""
    result: list[dict[str, object]] = []
    for message in messages:
        content = message.get("content")
        if mode == "never" or not isinstance(content, list):
            result.append(dict(message))
            continue
        parts = [p for p in content if isinstance(p, dict)]
        if mode == "text_only" and any(p.get("type") != "text" for p in parts):
            result.append(dict(message))
            continue
        if mode == "always" and any(p.get("type") != "text" for p in parts):
            logger.warning("Dropping non-text content parts: the provider API accepts text only")
        text = "".join(str(p["text"]) for p in parts if p.get("text"))
        result.append({**message, "content": text} if text else dict(message))
    return result


def _keeps_cache_control(route: Route) -> bool:
    mode = route.profile.cache_control
    return mode == "always" or (mode == "custom_base" and route.base_url != route.profile.base_url)


def _strip_cache_control(value: object) -> object:
    if isinstance(value, list):
        return [_strip_cache_control(item) for item in value]
    if isinstance(value, Mapping):
        return _strip_mapping(value)
    return value


def _strip_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    """``mapping`` with every nested ``cache_control`` mark removed: providers that do not know it reject the field."""
    return {k: _strip_cache_control(v) for k, v in mapping.items() if k != "cache_control"}


def _speaks_developer_role(route: Route) -> bool:
    """Only the vendor's own API is known to take the ``developer`` role; gateways and compatible APIs get ``system``."""
    return route.profile.id == "openai" and urlsplit(route.base_url or "").hostname == _OFFICIAL_HOST


def _demote_developer(messages: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [{**m, "role": "system"} if m.get("role") == "developer" else dict(m) for m in messages]


def drop_unsupported_temperature(profile: ProviderProfile, model: str, body: dict[str, object]) -> None:
    """Reasoning families accept no temperature other than 1."""
    if (
        profile.reasoning_model is not None
        and profile.reasoning_model.match(model)
        and body.get("temperature") not in (None, 1, 1.0)
    ):
        body.pop("temperature")


def _apply_reasoning_model_rules(profile: ProviderProfile, model: str, body: dict[str, object]) -> None:
    """Reasoning families take `max_completion_tokens` in place of `max_tokens`."""
    if profile.reasoning_model is None or not profile.reasoning_model.match(model):
        return
    if "max_tokens" in body:
        body.setdefault("max_completion_tokens", body.pop("max_tokens"))
    drop_unsupported_temperature(profile, model, body)


def openai_endpoint(route: Route, opts: CallOptions, path: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """(URL, query, headers) for ``path`` under the route's OpenAI-family endpoint."""
    base = route.base_url
    if not base:
        raise UnsupportedProviderError(f"Provider '{route.profile.id}' needs an api_base: it has no default endpoint")
    headers: dict[str, str] = dict(route.profile.headers)
    query: dict[str, str] = {}
    if route.profile.wire == "azure_openai":
        if path == "/responses":  # the Responses API addresses the model in the body, not by deployment
            url = f"{base}/openai{path}"
            query["api-version"] = opts.api_version or _DEFAULT_AZURE_RESPONSES_API_VERSION
        else:
            url = f"{base}/openai/deployments/{route.model}{path}"
            query["api-version"] = opts.api_version or _DEFAULT_AZURE_API_VERSION
        if route.api_key:
            headers["api-key"] = route.api_key
    else:
        url = f"{base}{path}"
        if route.api_key:
            headers["Authorization"] = f"Bearer {route.api_key}"
        if opts.organization and route.profile.id == "openai":
            headers["OpenAI-Organization"] = opts.organization
    return url, query, merge_headers(headers, opts.headers)


def prepare(route: Route, messages: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> PreparedRequest:
    opts = split_params(params)
    profile = route.profile
    params_body = opts.body
    if not _keeps_cache_control(route):
        messages = [_strip_mapping(m) for m in messages]
        params_body = _strip_mapping(params_body)
    if not _speaks_developer_role(route):
        messages = _demote_developer(messages)
    body: dict[str, object] = {"model": route.model, "messages": _flatten_text(messages, profile.flatten_text)}
    body.update(params_body)
    if not opts.stream:
        body.pop("stream", None)
        body.pop("stream_options", None)  # the API rejects stream options on a non-streaming call
    for key, value in profile.extra_body.items():
        body.setdefault(key, value)
    _apply_reasoning_model_rules(profile, route.model, body)
    body.update(opts.extra_body)
    url, query, headers = openai_endpoint(route, opts, "/chat/completions")
    return PreparedRequest(
        provider=profile.id,
        url=url,
        headers=headers,
        body=body,
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
        query=query,
    )


def _report_cache_hits(payload: dict[str, object]) -> None:
    """Mirror a top-level cache-read count of ``usage`` into ``prompt_tokens_details.cached_tokens``."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return
    hits = next(
        (
            value
            for key in _TOP_LEVEL_CACHE_READ_KEYS
            if isinstance(value := usage.get(key), int) and not isinstance(value, bool) and value > 0
        ),
        0,
    )
    if not hits:
        return
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        usage["prompt_tokens_details"] = {"cached_tokens": hits}
    elif not details.get("cached_tokens"):
        details["cached_tokens"] = hits


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    _report_cache_hits(payload)
    return payload


class OpenAIChunkDecoder:
    """SSE ``data:`` events are chat.completion.chunk objects; ``[DONE]`` ends the stream."""

    __slots__ = ("_provider", "done")

    def __init__(self, provider: str) -> None:
        self._provider = provider
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        if data.strip() == "[DONE]":
            self.done = True
            return []
        try:
            chunk = json.loads(data)
        except ValueError:
            logger.debug("Skipping a non-JSON stream event from %s", self._provider)
            return []
        if not isinstance(chunk, dict):
            return []
        if "error" in chunk and not chunk.get("choices"):
            raise LLMStreamError(self._provider, chunk)
        _report_cache_hits(chunk)
        return [chunk]

    def finish(self) -> list[Chunk]:
        return []


def decoder(route: Route) -> StreamDecoder:
    return OpenAIChunkDecoder(route.profile.id)
