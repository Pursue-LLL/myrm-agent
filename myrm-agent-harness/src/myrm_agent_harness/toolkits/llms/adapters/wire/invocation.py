"""Responses wire invocation helpers for TransportChatModel mixins.

[INPUT]
- logging::logging (POS: Python 标准日志库)
- collections.abc::AsyncIterator, Iterator (POS: Python 迭代器抽象类型)
- toolkits.llms.transport::LLMTransport (POS: the transport whose ``responses`` / ``aresponses`` calls are made)
- toolkits.llms.adapters.wire.normalizer::assert_responses_payload_not_failed, responses_stream_failure,
  responses_dict_to_chat_completion, responses_event_to_completion_chunk
  (POS: Responses wire 响应归一化层)
- toolkits.llms.adapters.wire.params::build_responses_kwargs
  (POS: Responses wire 请求装配层)
- toolkits.llms.adapters.wire.responses_stream::ResponsesStreamState
  (POS: 单次流内 function call / reasoning 的跨事件状态)

[OUTPUT]
- strip_reasoning_replay: message dicts without the Responses-only reasoning replay items
- invoke_responses_sync / invoke_responses_async: normalized chat.completion dicts
- stream_responses_sync / stream_responses_async: chunk iterators with a terminal
  finish_reason; failed streams raise ResponsesStreamError

[POS]
Transport adapter between TransportChatModel mixins and the Responses wire. Owns call assembly
and stream plumbing, delegating payload shaping to translator/params/normalizer. Retries
once without reasoning replay when the server rejects `invalid_encrypted_content`. The transport hands out
plain JSON objects (the answer, or one object per stream event), so no provider SDK model is ever read here.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from typing import cast

from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import (
    assert_responses_payload_not_failed,
    responses_dict_to_chat_completion,
    responses_event_to_completion_chunk,
    responses_stream_failure,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.params import build_responses_kwargs
from myrm_agent_harness.toolkits.llms.adapters.wire.responses_stream import ResponsesStreamState
from myrm_agent_harness.toolkits.llms.transport import LLMTransport

logger = logging.getLogger(__name__)

Payload = dict[str, object]


def _is_invalid_encrypted_content_error(exc: BaseException) -> bool:
    return "invalid_encrypted_content" in str(exc).lower()


def strip_reasoning_replay(message_dicts: list[Payload]) -> list[Payload]:
    stripped: list[Payload] = []
    for msg in message_dicts:
        if not isinstance(msg, dict):
            continue
        if "responses_reasoning_items" not in msg:
            stripped.append(msg)
            continue
        copy = dict(msg)
        copy.pop("responses_reasoning_items", None)
        stripped.append(copy)
    return stripped


def _strip_reasoning_include(params: Payload) -> Payload:
    params_copy = dict(params)
    extra_body = params_copy.get("extra_body")
    if not isinstance(extra_body, dict):
        return params_copy
    extra_copy = dict(extra_body)
    extra_copy.pop("include", None)
    params_copy["extra_body"] = extra_copy
    return params_copy


def _normalize_responses_tools(raw_tools: list[Payload]) -> list[Payload]:
    """Convert OpenAI chat completion tools {type: 'function', function: {...}} to Responses API tools."""
    normalized: list[Payload] = []
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if tool.get("type") == "function" and isinstance(function, dict) and "name" in function:
            fields = {key: function[key] for key in ("name", "description", "parameters", "strict") if key in function}
            normalized.append({"type": "function", **fields})
        else:
            normalized.append(tool)
    return normalized


def _responses_kwargs(message_dicts: list[Payload], params: Payload, *, stream: bool = False) -> Payload:
    """The ``responses`` call arguments: chat params translated, tools in the Responses shape."""
    kwargs = build_responses_kwargs(message_dicts, {**params, "stream": True} if stream else params)
    tools = kwargs.get("tools")
    if isinstance(tools, list):
        kwargs["tools"] = _normalize_responses_tools(tools)
    return kwargs


def _replay_free_kwargs(message_dicts: list[Payload], params: Payload, *, stream: bool = False) -> Payload:
    """The same call without the reasoning replay items and the ``include`` the server rejected."""
    return _responses_kwargs(strip_reasoning_replay(message_dicts), _strip_reasoning_include(params), stream=stream)


def _completion_of(answer: Payload) -> Payload:
    assert_responses_payload_not_failed(answer)
    return responses_dict_to_chat_completion(answer)


def invoke_responses_sync(client: LLMTransport, message_dicts: list[Payload], params: Payload) -> Payload:
    kwargs = _responses_kwargs(message_dicts, params)
    try:
        answer = client.responses(**kwargs)
    except Exception as exc:
        if not _is_invalid_encrypted_content_error(exc):
            raise
        logger.warning("Responses reasoning replay rejected; retrying without include/replay items")
        answer = client.responses(**_replay_free_kwargs(message_dicts, params))
    return _completion_of(cast(Payload, answer))


async def invoke_responses_async(client: LLMTransport, message_dicts: list[Payload], params: Payload) -> Payload:
    kwargs = _responses_kwargs(message_dicts, params)
    try:
        answer = await client.aresponses(**kwargs)
    except Exception as exc:
        if not _is_invalid_encrypted_content_error(exc):
            raise
        logger.warning("Responses reasoning replay rejected; retrying without include/replay items")
        answer = await client.aresponses(**_replay_free_kwargs(message_dicts, params))
    return _completion_of(cast(Payload, answer))


def _iter_responses_stream(client: LLMTransport, message_dicts: list[Payload], params: Payload) -> Iterator[Payload]:
    kwargs = _responses_kwargs(message_dicts, params, stream=True)
    try:
        yield from cast(Iterator[Payload], client.responses(**kwargs))
    except Exception as exc:
        if not _is_invalid_encrypted_content_error(exc):
            raise
        logger.warning("Responses reasoning replay rejected; retrying stream without include/replay items")
        yield from cast(Iterator[Payload], client.responses(**_replay_free_kwargs(message_dicts, params, stream=True)))


async def _aiter_responses_stream(
    client: LLMTransport, message_dicts: list[Payload], params: Payload
) -> AsyncIterator[Payload]:
    kwargs = _responses_kwargs(message_dicts, params, stream=True)
    try:
        stream = await client.aresponses(**kwargs)
    except Exception as exc:
        if not _is_invalid_encrypted_content_error(exc):
            raise
        logger.warning("Responses reasoning replay rejected; retrying stream without include/replay items")
        stream = await client.aresponses(**_replay_free_kwargs(message_dicts, params, stream=True))
    async for event in cast(AsyncIterator[Payload], stream):
        yield event


async def stream_responses_async(
    client: LLMTransport, message_dicts: list[Payload], params: Payload
) -> AsyncIterator[Payload]:
    state = ResponsesStreamState()
    async for event in _aiter_responses_stream(client, message_dicts, params):
        if failure := responses_stream_failure(event):
            raise failure
        chunk = responses_event_to_completion_chunk(event, state)
        if chunk is not None:
            yield chunk


def stream_responses_sync(client: LLMTransport, message_dicts: list[Payload], params: Payload) -> Iterator[Payload]:
    state = ResponsesStreamState()
    for event in _iter_responses_stream(client, message_dicts, params):
        if failure := responses_stream_failure(event):
            raise failure
        chunk = responses_event_to_completion_chunk(event, state)
        if chunk is not None:
            yield chunk
