"""OpenAI Responses wire: request building, response and event decoding.

[INPUT]
- transport.openai_chat (POS: openai_endpoint — URL and credential headers of the OpenAI family)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest, StreamDecoder)

[OUTPUT]
- prepare: a PreparedRequest for ``POST {base}/responses``
- parse: the provider's JSON answer (identity; the adapter's normalizer reads the Responses object)
- decoder: the SSE decoder yielding Responses event dicts

[POS]
The adapter assembles the full Responses body itself (input items, instructions, reasoning, tools), so this wire
only adds routing: endpoint, credential, ``extra_body`` overlay and event framing. Events are handed over as the
provider sent them; ``response.completed`` / ``response.failed`` / ``response.incomplete`` end the stream.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.errors import LLMStreamError
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, PreparedRequest, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.openai_chat import drop_unsupported_temperature, openai_endpoint
from myrm_agent_harness.toolkits.llms.transport.params import split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError

logger = logging.getLogger(__name__)

_TERMINAL_EVENTS: Final = frozenset({"response.completed", "response.failed", "response.incomplete"})


def prepare(route: Route, params: Mapping[str, object]) -> PreparedRequest:
    if not route.profile.responses:
        raise UnsupportedProviderError(f"Provider '{route.profile.id}' has no Responses endpoint")
    opts = split_params(params)
    body: dict[str, object] = {"model": route.model, **opts.body}
    drop_unsupported_temperature(route.profile, route.model, body)
    if not opts.stream:
        body.pop("stream", None)
    # Native search has no Responses parameter; xAI serves it as a `web_search` tool, other providers take none.
    search = body.pop("web_search_options", None)
    if search is not None and route.profile.id == "xai":
        tools = body.get("tools")
        body["tools"] = [*(tools if isinstance(tools, list) else []), {"type": "web_search"}]
    body.update(opts.extra_body)
    url, query, headers = openai_endpoint(route, opts, "/responses")
    return PreparedRequest(
        provider=route.profile.id,
        url=url,
        headers=headers,
        body=body,
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
        query=query,
    )


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    return payload


class ResponsesEventDecoder:
    __slots__ = ("_provider", "done")

    def __init__(self, provider: str) -> None:
        self._provider = provider
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        if data.strip() == "[DONE]":
            self.done = True
            return []
        try:
            payload = json.loads(data)
        except ValueError:
            logger.debug("Skipping a non-JSON stream event from %s", self._provider)
            return []
        if not isinstance(payload, dict):
            return []
        kind = payload.get("type") or event
        if "type" not in payload and "error" in payload:
            raise LLMStreamError(self._provider, payload)
        if kind in _TERMINAL_EVENTS:
            self.done = True
        return [payload]

    def finish(self) -> list[Chunk]:
        return []


def decoder(route: Route) -> StreamDecoder:
    return ResponsesEventDecoder(route.profile.id)
