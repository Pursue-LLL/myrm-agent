"""Anthropic Messages wire: OpenAI-shaped input to ``POST /v1/messages``.

[INPUT]
- transport.profile (POS: Route — endpoint root and credential)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest)
- transport.anthropic_schema (POS: structured-output schema conversion)

[OUTPUT]
- prepare: a PreparedRequest for ``POST {base}/v1/messages``

[POS]
Request half of the Anthropic wire (answers are read by ``anthropic_response``). Messages and tools arrive
OpenAI-shaped and leave as content blocks; cache_control markers on content parts, tools and system blocks are
carried through unchanged; consecutive turns of one role are merged because the API demands alternation. Extended
thinking is switched off for a turn whose earlier tool calls carry no signed thinking block, because the API
rejects such a replay.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Final
from urllib.parse import urlsplit

from myrm_agent_harness.toolkits.llms.transport.anthropic_schema import to_output_schema
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.llms.transport.params import CallOptions, merge_headers, split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError

logger = logging.getLogger(__name__)

_API_VERSION: Final = "2023-06-01"
_OFFICIAL_HOST: Final = "api.anthropic.com"
_STRUCTURED_OUTPUT_BETA: Final = "structured-outputs-2025-11-13"
_THINKING_TYPES: Final = ("thinking", "redacted_thinking")
_DEFAULT_MAX_TOKENS: Final = 8192
_DATA_URL: Final = re.compile(r"^data:(?P<media>[^;,]+);base64,(?P<data>.+)$", re.DOTALL)
_THINKING_BUDGET: Final = {"minimal": 1024, "low": 1024, "medium": 2048, "high": 4096, "xhigh": 8192, "max": 8192}
_DISABLED_EFFORT: Final = frozenset({"none", "off", "disable", "disabled"})
Block = dict[str, object]


# --- request ---------------------------------------------------------------------------------------------------


def _cache_control(part: Mapping[str, object]) -> dict[str, object]:
    marker = part.get("cache_control")
    return {"cache_control": dict(marker)} if isinstance(marker, Mapping) else {}


def _image_block(part: Mapping[str, object]) -> Block | None:
    image = part.get("image_url")
    url = image.get("url") if isinstance(image, Mapping) else image
    if not isinstance(url, str) or not url:
        return None
    match = _DATA_URL.match(url)
    source: dict[str, object] = (
        {"type": "base64", "media_type": match["media"], "data": match["data"]}
        if match
        else {"type": "url", "url": url}
    )
    return {"type": "image", "source": source, **_cache_control(part)}


def _file_block(part: Mapping[str, object]) -> Block | None:
    file = part.get("file")
    data = file.get("file_data") if isinstance(file, Mapping) else None
    match = _DATA_URL.match(data) if isinstance(data, str) else None
    if match is None:
        return None
    source = {"type": "base64", "media_type": match["media"], "data": match["data"]}
    return {"type": "document", "source": source, **_cache_control(part)}


def _content_blocks(content: object) -> list[Block]:
    """OpenAI ``content`` (string or parts) as Anthropic content blocks; empty text blocks are rejected by the API."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks: list[Block] = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, str):
            if part:
                blocks.append({"type": "text", "text": part})
            continue
        if not isinstance(part, Mapping):
            continue
        kind = part.get("type")
        block: Block | None = None
        if kind == "text":
            text = part.get("text")
            block = {"type": "text", "text": text, **_cache_control(part)} if isinstance(text, str) and text else None
        elif kind == "image_url":
            block = _image_block(part)
        elif kind == "file":
            block = _file_block(part)
        else:
            logger.warning("Dropping content part of unsupported type %r for the Anthropic Messages API", kind)
        if block is not None:
            blocks.append(block)
    return blocks


def _tool_use_blocks(tool_calls: object) -> list[Block]:
    blocks: list[Block] = []
    for call in tool_calls if isinstance(tool_calls, list) else []:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        raw = function.get("arguments")
        try:
            arguments = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except ValueError:
            arguments = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or "",
                "name": function.get("name") or "",
                "input": arguments if isinstance(arguments, dict) else {},
            }
        )
    return blocks


def _tool_result_block(message: Mapping[str, object]) -> Block:
    content = message.get("content")
    block: Block = {"type": "tool_result", "tool_use_id": message.get("tool_call_id") or ""}
    if isinstance(content, str):
        if content:
            block["content"] = content
    else:
        parts = _content_blocks(content)
        if parts:
            block["content"] = parts
    return block


def _thinking_blocks(message: Mapping[str, object]) -> list[Block]:
    """Signed thinking blocks the previous answer carried; unsigned reasoning text cannot be replayed."""
    blocks = message.get("thinking_blocks")
    return (
        [dict(b) for b in blocks if isinstance(b, Mapping) and b.get("signature")] if isinstance(blocks, list) else []
    )


def _to_messages(messages: Sequence[Mapping[str, object]]) -> tuple[list[Block], list[Block]]:
    """(system blocks, alternating user/assistant messages) for the Messages API."""
    system: list[Block] = []
    turns: list[tuple[str, list[Block]]] = []

    def push(role: str, blocks: list[Block]) -> None:
        if not blocks:
            return
        if turns and turns[-1][0] == role:
            turns[-1][1].extend(blocks)
        else:
            turns.append((role, list(blocks)))

    for message in messages:
        role = message.get("role")
        if role in ("system", "developer"):
            system.extend(_content_blocks(message.get("content")))
        elif role == "assistant":
            push(
                "assistant",
                _thinking_blocks(message)
                + _content_blocks(message.get("content"))
                + _tool_use_blocks(message.get("tool_calls")),
            )
        elif role == "tool":
            # tool_result blocks must lead the user turn that answers the tool calls
            result = _tool_result_block(message)
            if turns and turns[-1][0] == "user":
                blocks = turns[-1][1]
                blocks.insert(sum(1 for b in blocks if b.get("type") == "tool_result"), result)
            else:
                push("user", [result])
        elif role == "user":
            push("user", _content_blocks(message.get("content")))
    if turns and turns[0][0] != "user":
        turns.insert(0, ("user", [{"type": "text", "text": "."}]))
    return system, [{"role": role, "content": blocks} for role, blocks in turns]


def _tools(raw: object, web_search: Mapping[str, object] | None) -> list[Block]:
    tools: list[Block] = []
    for tool in raw if isinstance(raw, list) else []:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if not isinstance(function, Mapping):
            if isinstance(tool, Mapping) and tool.get("type") not in (None, "function"):
                tools.append(dict(tool))  # an Anthropic server tool passed through untouched
            continue
        parameters = function.get("parameters")
        entry: Block = {
            "name": function.get("name"),
            "input_schema": dict(parameters)
            if isinstance(parameters, Mapping)
            else {"type": "object", "properties": {}},
            "type": "custom",
        }
        if function.get("description"):
            entry["description"] = function["description"]
        entry.update(_cache_control(function) or _cache_control(tool))
        tools.append(entry)
    if web_search is not None:
        search: Block = {"type": "web_search_20250305", "name": "web_search"}
        if isinstance(web_search.get("max_uses"), int):
            search["max_uses"] = web_search["max_uses"]
        tools.append(search)
    return tools


def _tool_choice(choice: object, parallel: object) -> Block | None:
    disable_parallel = parallel is False
    if choice in (None, "auto"):
        kind: Block = {"type": "auto"}
    elif choice == "required":
        kind = {"type": "any"}
    elif choice == "none":
        return {"type": "none"}
    elif isinstance(choice, Mapping):
        function = choice.get("function")
        name = function.get("name") if isinstance(function, Mapping) else choice.get("name")
        kind = {"type": "tool", "name": name} if name else {"type": "auto"}
    else:
        return None
    kind["disable_parallel_tool_use"] = disable_parallel
    return kind


def _thinking(body_params: Mapping[str, object]) -> Block | None:
    explicit = body_params.get("thinking")
    if isinstance(explicit, Mapping):
        return dict(explicit)
    effort = body_params.get("reasoning_effort")
    if not isinstance(effort, str) or effort.lower() in _DISABLED_EFFORT:
        return None
    budget = _THINKING_BUDGET.get(effort.lower())
    return {"type": "enabled", "budget_tokens": budget} if budget else None


def _stop_sequences(stop: object) -> list[str] | None:
    if isinstance(stop, str):
        return [stop]
    if isinstance(stop, list):
        return [s for s in stop if isinstance(s, str)] or None
    return None


def _lacks_thinking_replay(turns: Sequence[Mapping[str, object]]) -> bool:
    """Whether an assistant turn calls tools without the thinking block the API demands first when thinking is on."""
    for turn in turns:
        blocks = turn.get("content")
        if turn.get("role") != "assistant" or not isinstance(blocks, list):
            continue
        calls_tool = any(isinstance(b, Mapping) and b.get("type") == "tool_use" for b in blocks)
        leads = bool(blocks) and isinstance(blocks[0], Mapping) and blocks[0].get("type") in _THINKING_TYPES
        if calls_tool and not leads:
            return True
    return False


def _body(route: Route, messages: Sequence[Mapping[str, object]], opts: CallOptions) -> dict[str, object]:
    params = opts.body
    system, turns = _to_messages(messages)
    max_tokens = params.get("max_completion_tokens") or params.get("max_tokens")
    body: dict[str, object] = {
        "model": route.model,
        "max_tokens": max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else _DEFAULT_MAX_TOKENS,
        "messages": turns,
    }
    if system:
        body["system"] = system
    thinking = _thinking(params)
    if thinking is not None and _lacks_thinking_replay(turns):
        logger.info("Thinking is off for this turn: earlier tool calls carry no signed thinking block to replay")
        thinking = None
    if thinking is not None:
        body["thinking"] = thinking
    # Extended thinking accepts only the default sampling: the API rejects an explicit temperature or top_k.
    if thinking is None or thinking.get("type") == "disabled":
        for key in ("temperature", "top_p", "top_k"):
            if params.get(key) is not None:
                body[key] = params[key]
    stop = _stop_sequences(params.get("stop"))
    if stop:
        body["stop_sequences"] = stop
    web_search = params.get("web_search_options")
    tools = _tools(params.get("tools"), web_search if isinstance(web_search, Mapping) else None)
    if tools:
        body["tools"] = tools
        choice = _tool_choice(params.get("tool_choice"), params.get("parallel_tool_calls"))
        if choice is not None:
            body["tool_choice"] = choice
    response_format = params.get("response_format")
    if isinstance(response_format, Mapping) and response_format.get("type") == "json_schema":
        schema_holder = response_format.get("json_schema")
        schema = schema_holder.get("schema") if isinstance(schema_holder, Mapping) else None
        if isinstance(schema, Mapping):
            body["output_format"] = {"type": "json_schema", "schema": to_output_schema(schema)}
    user = params.get("user")
    if isinstance(user, str) and user:
        body["metadata"] = {"user_id": user}
    if opts.stream:
        body["stream"] = True
    body.update(opts.extra_body)
    return body


def _merge_beta(headers: dict[str, str], required: str | None) -> dict[str, str]:
    """Caller-supplied ``anthropic-beta`` flags are kept next to the one the request itself needs."""
    if required is None:
        return headers
    key = next((k for k in headers if k.lower() == "anthropic-beta"), "anthropic-beta")
    flags = [f.strip() for f in headers.get(key, "").split(",") if f.strip()]
    if required not in flags:
        flags.append(required)
    return {**headers, key: ",".join(flags)}


def prepare(route: Route, messages: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> PreparedRequest:
    opts = split_params(params)
    if not route.base_url:
        raise UnsupportedProviderError("The Anthropic wire needs an api_base")
    body = _body(route, messages, opts)
    headers: dict[str, str] = {"anthropic-version": _API_VERSION}
    if route.api_key:
        headers["x-api-key"] = route.api_key
        # Gateways that front the Messages API authenticate with a bearer token; the vendor itself never needs one.
        if urlsplit(route.base_url).hostname != _OFFICIAL_HOST:
            headers["authorization"] = f"Bearer {route.api_key}"
    if "output_format" in body:
        headers["anthropic-beta"] = _STRUCTURED_OUTPUT_BETA
    return PreparedRequest(
        provider=route.profile.id,
        url=f"{route.base_url}/v1/messages",
        headers=_merge_beta(merge_headers(headers, opts.headers), headers.get("anthropic-beta")),
        body=body,
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
    )
