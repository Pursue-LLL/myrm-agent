"""OpenAI Responses wire: request building, response and event decoding.

[INPUT]
- transport.openai_chat (POS: openai_endpoint — URL and credential headers of the OpenAI family)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest, StreamDecoder)
- transport.frames (POS: the JSON payload of a stream frame)

[OUTPUT]
- prepare: a PreparedRequest for ``POST {base}/responses``
- parse: the provider's JSON answer (the adapter's normalizer reads the Responses object); a bare error body raises
- decoder: the SSE decoder yielding Responses event dicts

[POS]
The adapter assembles the full Responses body itself (input items, instructions, reasoning, tools), so this wire
only adds routing: endpoint, credential, ``extra_body`` overlay and event framing. Events are handed over as the
provider sent them; ``response.completed`` / ``response.failed`` / ``response.incomplete`` end the stream.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.frames import json_frame
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, PreparedRequest, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.openai_chat import drop_unsupported_temperature, openai_endpoint
from myrm_agent_harness.toolkits.llms.transport.params import split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

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
        retries=DEFAULT_RETRIES,
    )


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    # A Response object carries a status or an output; a body with an error and neither is the provider's refusal
    # to answer. (A ``failed`` Response is the adapter's to read: it names the failure in the provider's words.)
    if payload.get("error") and "status" not in payload and "output" not in payload:
        raise LLMAnswerError(route.profile.id, payload)
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
        payload = json_frame(self._provider, data)
        if payload is None:
            return []
        kind = payload.get("type") or event
        if "type" not in payload and payload.get("error"):
            raise LLMAnswerError(self._provider, payload, stream=True)
        if kind in _TERMINAL_EVENTS:
            self.done = True
        return [payload]

    def finish(self) -> list[Chunk]:
        return []


def decoder(route: Route) -> StreamDecoder:
    return ResponsesEventDecoder(route.profile.id)
