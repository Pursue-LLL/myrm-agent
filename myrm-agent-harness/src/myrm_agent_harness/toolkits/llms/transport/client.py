"""LLMTransport: the single entry the chat adapter calls to reach any provider.

[INPUT]
- transport.profile (POS: resolve_route — provider, endpoint and credential of a call)
- transport.http (POS: request execution and stream iterators)
- transport.chat_shape (POS: the chat.completion shape the adapter reads, applied to every chat answer)
- transport.answer_cache (POS: replays the answer of a request that was already answered)
- transport.openai_chat / openai_responses / anthropic_messages / anthropic_response / bedrock_converse / bedrock_response / gemini_generate / ollama_chat (POS: the wires)

[OUTPUT]
- LLMTransport: ``completion`` / ``acompletion`` (chat) and ``responses`` / ``aresponses`` (Responses wire)
- get_transport: the shared stateless instance

[POS]
Facade over the wires: resolve the route, let the wire build the provider request, execute it, and return the answer
in the OpenAI chat shape (dict, or an iterator of chunk dicts when streaming); ``chat_shape`` guarantees that shape
whichever wire or gateway produced the answer. A request that was already answered is answered from ``answer_cache``
instead of the provider. The facade keeps no state of its own, so one instance serves every model and thread;
connection pools live in ``http``. It exposes the same four calls and keyword arguments the chat adapter has always
issued, which keeps the adapter's retry, failover and recovery logic untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_messages,
    anthropic_response,
    bedrock_converse,
    bedrock_response,
    gemini_generate,
    ollama_chat,
    openai_chat,
    openai_responses,
)
from myrm_agent_harness.toolkits.llms.transport.answer_cache import (
    CHAT,
    RESPONSES,
    AsyncReplayStream,
    ReplayStream,
    acached_answer,
    acached_stream,
    cached_answer,
    cached_stream,
)
from myrm_agent_harness.toolkits.llms.transport.chat_shape import ShapedDecoder, shape_completion
from myrm_agent_harness.toolkits.llms.transport.http import (
    AsyncProviderStream,
    PreparedRequest,
    ProviderStream,
    StreamDecoder,
    aopen_stream,
    asend_json,
    open_stream,
    send_json,
)
from myrm_agent_harness.toolkits.llms.transport.profile import Route, resolve_route

Messages = Sequence[Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class ChatWire:
    """The three functions every chat wire module provides."""

    prepare: Callable[[Route, Messages, Mapping[str, object]], PreparedRequest]
    parse: Callable[[Route, dict[str, object]], dict[str, object]]
    decoder: Callable[[Route], StreamDecoder]


_OPENAI = ChatWire(openai_chat.prepare, openai_chat.parse, openai_chat.decoder)
_CHAT_WIRES: Final[dict[str, ChatWire]] = {
    "openai_chat": _OPENAI,
    "azure_openai": _OPENAI,
    "anthropic": ChatWire(anthropic_messages.prepare, anthropic_response.parse, anthropic_response.decoder),
    "gemini": ChatWire(gemini_generate.prepare, gemini_generate.parse, gemini_generate.decoder),
    "ollama": ChatWire(ollama_chat.prepare, ollama_chat.parse, ollama_chat.decoder),
    "bedrock": ChatWire(bedrock_converse.prepare, bedrock_response.parse, bedrock_response.decoder),
}


def _route(params: Mapping[str, object]) -> Route:
    def text(key: str) -> str | None:
        value = params.get(key)
        return value if isinstance(value, str) and value else None

    return resolve_route(
        str(params.get("model") or ""),
        custom_llm_provider=text("custom_llm_provider"),
        api_base=text("api_base") or text("base_url"),
        api_key=text("api_key"),
    )


class LLMTransport:
    """Provider transport without state of its own; see the module docstring."""

    def completion(self, *, messages: Messages, **params: object) -> dict[str, object] | ProviderStream | ReplayStream:
        route = _route(params)
        wire = _CHAT_WIRES[route.profile.wire]
        request = wire.prepare(route, messages, params)
        if request.stream:
            return cached_stream(open_stream, request, ShapedDecoder(wire.decoder(route)), CHAT)
        return cached_answer(
            request, lambda: shape_completion(route.profile.id, wire.parse(route, send_json(request))), keep=CHAT.answer
        )

    async def acompletion(
        self, *, messages: Messages, **params: object
    ) -> dict[str, object] | AsyncProviderStream | AsyncReplayStream:
        route = _route(params)
        wire = _CHAT_WIRES[route.profile.wire]
        request = wire.prepare(route, messages, params)
        if request.stream:
            return await acached_stream(aopen_stream, request, ShapedDecoder(wire.decoder(route)), CHAT)

        async def answer() -> dict[str, object]:
            return shape_completion(route.profile.id, wire.parse(route, await asend_json(request)))

        return await acached_answer(request, answer, keep=CHAT.answer)

    def responses(self, **params: object) -> dict[str, object] | ProviderStream | ReplayStream:
        route = _route(params)
        request = openai_responses.prepare(route, params)
        if request.stream:
            return cached_stream(open_stream, request, openai_responses.decoder(route), RESPONSES)
        return cached_answer(request, lambda: openai_responses.parse(route, send_json(request)), keep=RESPONSES.answer)

    async def aresponses(self, **params: object) -> dict[str, object] | AsyncProviderStream | AsyncReplayStream:
        route = _route(params)
        request = openai_responses.prepare(route, params)
        if request.stream:
            return await acached_stream(aopen_stream, request, openai_responses.decoder(route), RESPONSES)

        async def answer() -> dict[str, object]:
            return openai_responses.parse(route, await asend_json(request))

        return await acached_answer(request, answer, keep=RESPONSES.answer)


@lru_cache(maxsize=1)
def get_transport() -> LLMTransport:
    return LLMTransport()
