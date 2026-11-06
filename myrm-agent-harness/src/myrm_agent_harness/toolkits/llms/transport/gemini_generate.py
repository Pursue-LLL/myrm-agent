"""Gemini generateContent wire: OpenAI-shaped input to ``models/{model}:generateContent`` and back.

[INPUT]
- transport.capabilities (POS: gemini_from_3, gemini_thinks_by_level, gemini_thinking_level — what a Gemini generation takes)
- transport.gemini_contents (POS: history as alternating turns, the call-id signature convention)
- transport.gemini_schema (POS: tool-parameter schema reduction to the Gemini subset)
- transport.profile (POS: Route — endpoint root and credential)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.chat_shape (POS: answered_without, the failure of a 200 answer that holds no candidate)
- transport.http (POS: PreparedRequest, StreamDecoder)

[OUTPUT]
- prepare: a PreparedRequest for ``generateContent`` / ``streamGenerateContent?alt=sse``
- parse: a GenerateContentResponse as a chat.completion dict (content, reasoning, tool_calls, usage)
- decoder: the SSE decoder yielding chat.completion.chunk dicts

[POS]
Translation boundary for the Gemini API (first-party and Gemini-compatible gateways, which speak this native
wire rather than the OpenAI one). Messages become ``contents`` (``gemini_contents``), tools become function
declarations, the system prompt becomes ``system_instruction``. Gemini 3 hands out a ``thoughtSignature`` with each
function call and demands it back on the next turn: the answer side folds it into the tool-call id
(``<id>__thought__<signature>``), the one field every layer above preserves verbatim, so no other layer needs to know
about it.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Final
from urllib.parse import urlsplit

from myrm_agent_harness.toolkits.llms.transport.capabilities import (
    gemini_from_3,
    gemini_thinking_level,
    gemini_thinks_by_level,
)
from myrm_agent_harness.toolkits.llms.transport.chat_shape import answered_without
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.frames import json_frame
from myrm_agent_harness.toolkits.llms.transport.gemini_contents import SIGNATURE_SEPARATOR, Part, to_contents
from myrm_agent_harness.toolkits.llms.transport.gemini_schema import to_gemini_schema
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, PreparedRequest, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.params import CallOptions, merge_headers, split_params
from myrm_agent_harness.toolkits.llms.transport.profile import GEMINI_OFFICIAL_HOST, Route, UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

logger = logging.getLogger(__name__)

_THINKING_BUDGET: Final = {"low": 1024, "medium": 2048, "high": 4096, "xhigh": 8192, "max": 8192}
_DISABLED_EFFORT: Final = frozenset({"none", "off", "disable", "disabled"})
_JSON_OUTPUT: Final = ("responseMimeType", "responseJsonSchema")
_FILTERED: Final = frozenset(
    {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
        "LANGUAGE",
        "IMAGE_PROHIBITED_CONTENT",
    }
)


# --- request ---------------------------------------------------------------------------------------------------


def _thinking_budget(model: str, level: str) -> int | None:
    """Token budget of a 2.x model for an effort; ``minimal`` is the smallest the model takes (Pro 128, Flash-Lite 512)."""
    if level != "minimal":
        return _THINKING_BUDGET.get(level)
    name = model.lower()
    if "pro" in name:
        return 128
    return 512 if "flash-lite" in name else 1


def _thinking_off(model: str) -> Part:
    """Thinking switched off as far as the model allows: Gemini 3 has a lowest level, 2.5 Pro a budget floor."""
    if gemini_thinks_by_level(model):
        return {"includeThoughts": False, "thinkingLevel": gemini_thinking_level(model, "minimal")}
    return {"includeThoughts": False, "thinkingBudget": 128 if "pro" in model.lower() else 0}


def _thinking_config(model: str, effort: object) -> Part | None:
    if not isinstance(effort, str):
        return None
    level = effort.lower()
    if level in _DISABLED_EFFORT:
        return _thinking_off(model)
    if gemini_thinks_by_level(model):
        return {"includeThoughts": True, "thinkingLevel": gemini_thinking_level(model, level)}
    budget = _thinking_budget(model, level)
    return {"includeThoughts": True, "thinkingBudget": budget} if budget else None


def _generation_config(route: Route, params: Mapping[str, object]) -> Part:
    config: Part = {}
    limit = params.get("max_completion_tokens") or params.get("max_tokens")
    if isinstance(limit, int) and limit > 0:
        config["maxOutputTokens"] = limit
    for source, target in (
        ("temperature", "temperature"),
        ("top_p", "topP"),
        ("top_k", "topK"),
        ("seed", "seed"),
        ("presence_penalty", "presencePenalty"),
        ("frequency_penalty", "frequencyPenalty"),
    ):
        if params.get(source) is not None:
            config[target] = params[source]
    stop = params.get("stop")
    if isinstance(stop, str):
        config["stopSequences"] = [stop]
    elif isinstance(stop, list) and stop:
        config["stopSequences"] = [s for s in stop if isinstance(s, str)]
    response_format = params.get("response_format")
    if isinstance(response_format, Mapping) and response_format.get("type") in ("json_schema", "json_object"):
        config["responseMimeType"] = "application/json"
        holder = response_format.get("json_schema")
        schema = holder.get("schema") if isinstance(holder, Mapping) else None
        if isinstance(schema, Mapping):
            config["responseJsonSchema"] = dict(schema)
    thinking = _thinking_config(route.model, params.get("reasoning_effort"))
    if thinking is not None:
        config["thinkingConfig"] = thinking
    return config


def _tool_config(choice: object) -> Part | None:
    if choice in (None, "auto"):
        return {"functionCallingConfig": {"mode": "AUTO"}}
    if choice == "required":
        return {"functionCallingConfig": {"mode": "ANY"}}
    if choice == "none":
        return {"functionCallingConfig": {"mode": "NONE"}}
    if isinstance(choice, Mapping):
        function = choice.get("function")
        name = function.get("name") if isinstance(function, Mapping) else None
        if name:
            return {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [name]}}
    return None


def _declarations(raw: object) -> list[Part]:
    declarations: list[Part] = []
    for tool in raw if isinstance(raw, list) else []:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if not isinstance(function, Mapping) or not function.get("name"):
            continue
        entry: Part = {"name": function["name"]}
        if function.get("description"):
            entry["description"] = function["description"]
        parameters = function.get("parameters")
        if isinstance(parameters, Mapping) and parameters.get("properties"):
            entry["parameters"] = to_gemini_schema(parameters)
        declarations.append(entry)
    return declarations


def _forces_call(tool_config: Part | None) -> bool:
    calling = tool_config.get("functionCallingConfig") if tool_config else None
    return isinstance(calling, Mapping) and calling.get("mode") == "ANY"


def _body(route: Route, messages: Sequence[Mapping[str, object]], opts: CallOptions) -> dict[str, object]:
    params = opts.body
    gemini_3 = gemini_from_3(route.model)
    system, contents = to_contents(messages, gemini_3=gemini_3)
    body: dict[str, object] = {"contents": contents}
    if system:
        body["system_instruction"] = {"parts": system}
    config = _generation_config(route, params)
    declarations = _declarations(params.get("tools"))
    tool_config = _tool_config(params.get("tool_choice")) if declarations else None
    # The API refuses JSON output beside function declarations before Gemini 3, and beside a forced call on any model:
    # the tools win and the answer comes back unconstrained.
    if declarations and (not gemini_3 or _forces_call(tool_config)) and "responseMimeType" in config:
        logger.debug("Gemini cannot combine JSON output with these function tools; the response format is skipped")
        for key in _JSON_OUTPUT:
            config.pop(key, None)
    if config:
        body["generationConfig"] = config
    tools: list[Part] = []
    if declarations:
        tools.append({"functionDeclarations": declarations})
        if tool_config is not None:
            body["toolConfig"] = tool_config
    if isinstance(params.get("web_search_options"), Mapping):
        if declarations:
            logger.debug("Gemini cannot combine Google Search with function tools; search is skipped for this call")
        else:
            tools.append({"googleSearch": {}})
    if tools:
        body["tools"] = tools
    body.update(opts.extra_body)
    return body


def prepare(route: Route, messages: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> PreparedRequest:
    opts = split_params(params)
    if not route.base_url:
        raise UnsupportedProviderError("The Gemini wire needs an api_base")
    action = "streamGenerateContent" if opts.stream else "generateContent"
    model = route.model.removeprefix("models/")
    headers: dict[str, str] = {}
    if route.api_key:
        headers["x-goog-api-key"] = route.api_key
        if urlsplit(route.base_url).hostname != GEMINI_OFFICIAL_HOST:
            headers["Authorization"] = f"Bearer {route.api_key}"  # gateways that emulate the API read either header
    return PreparedRequest(
        provider=route.profile.id,
        url=f"{route.base_url}/models/{model}:{action}",
        headers=merge_headers(headers, opts.headers),
        body=_body(route, messages, opts),
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
        query={"alt": "sse"} if opts.stream else {},
        retries=DEFAULT_RETRIES,
    )


# --- response --------------------------------------------------------------------------------------------------


def _finish_reason(reason: object, has_tool_calls: bool) -> str:
    if has_tool_calls:
        return "tool_calls"
    if reason == "MAX_TOKENS":
        return "length"
    if reason in _FILTERED:
        return "content_filter"
    return "stop"


def _usage(raw: Mapping[str, object]) -> dict[str, object]:
    """Thought tokens are billed as output; ``promptTokenCount`` already contains the cached tokens."""

    def count(key: str) -> int:
        value = raw.get(key)
        return value if isinstance(value, int) else 0

    prompt, candidates, thoughts, cached = (
        count("promptTokenCount"),
        count("candidatesTokenCount"),
        count("thoughtsTokenCount"),
        count("cachedContentTokenCount"),
    )
    usage: dict[str, object] = {
        "prompt_tokens": prompt,
        "completion_tokens": candidates + thoughts,
        "total_tokens": count("totalTokenCount") or prompt + candidates + thoughts,
        "prompt_tokens_details": {"cached_tokens": cached},
    }
    if thoughts:
        usage["completion_tokens_details"] = {"reasoning_tokens": thoughts}
    return usage


def _tool_call(part: Mapping[str, object], index: int) -> Part | None:
    call = part.get("functionCall")
    if not isinstance(call, Mapping):
        return None
    call_id = f"call_{uuid.uuid4().hex[:24]}"
    signature = part.get("thoughtSignature")
    if isinstance(signature, str) and signature:
        call_id += SIGNATURE_SEPARATOR + signature
    return {
        "index": index,
        "id": call_id,
        "type": "function",
        "function": {"name": call.get("name"), "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False)},
    }


def _candidate(payload: Mapping[str, object]) -> Mapping[str, object]:
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else None
    return first if isinstance(first, Mapping) else {}


def _candidate_parts(candidate: Mapping[str, object]) -> list[Mapping[str, object]]:
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, Mapping) else None
    return [p for p in parts if isinstance(p, Mapping)] if isinstance(parts, list) else []


def _blocked(payload: Mapping[str, object]) -> bool:
    feedback = payload.get("promptFeedback")
    return isinstance(feedback, Mapping) and bool(feedback.get("blockReason"))


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("error") and not payload.get("candidates"):
        raise LLMAnswerError(route.profile.id, payload)
    # A blocked prompt has no candidates, but its verdict is in promptFeedback; a body with neither is no answer.
    if not isinstance(payload.get("candidates"), list) and not isinstance(payload.get("promptFeedback"), Mapping):
        raise answered_without(route.profile.id, "a candidate", payload)
    candidate = _candidate(payload)
    texts: list[str] = []
    reasoning: list[str] = []
    tool_calls: list[Part] = []
    for part in _candidate_parts(candidate):
        call = _tool_call(part, len(tool_calls))
        if call is not None:
            tool_calls.append(call)
        elif isinstance(part.get("text"), str):
            (reasoning if part.get("thought") is True else texts).append(str(part["text"]))
    message: Part = {"role": "assistant", "content": "".join(texts) or None}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    if tool_calls:
        message["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in tool_calls]
    usage = payload.get("usageMetadata")
    reason = (
        "content_filter"
        if _blocked(payload) and not candidate
        else _finish_reason(candidate.get("finishReason"), bool(tool_calls))
    )
    return {
        "id": payload.get("responseId") or f"gemini-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": payload.get("modelVersion") or route.model,
        "choices": [{"index": 0, "message": message, "finish_reason": reason}],
        "usage": _usage(usage) if isinstance(usage, Mapping) else {},
    }


# --- stream ----------------------------------------------------------------------------------------------------


class GeminiStreamDecoder:
    """One SSE event is a partial GenerateContentResponse; the event carrying ``finishReason`` closes the answer."""

    __slots__ = ("_id", "_model", "_provider", "_tool_index", "done")

    def __init__(self, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._id = f"gemini-{uuid.uuid4().hex[:12]}"
        self._tool_index = -1
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        payload = json_frame(self._provider, data)
        if payload is None:
            return []
        if payload.get("error") and not payload.get("candidates"):
            raise LLMAnswerError(self._provider, payload, stream=True)
        self._model = str(payload.get("modelVersion") or self._model)
        candidate = _candidate(payload)
        delta: Part = {}
        calls: list[Part] = []
        for part in _candidate_parts(candidate):
            call = _tool_call(part, self._tool_index + 1)
            if call is not None:
                self._tool_index += 1
                calls.append(call)
            elif isinstance(part.get("text"), str) and part["text"]:
                key = "reasoning_content" if part.get("thought") is True else "content"
                delta[key] = str(delta.get(key, "")) + str(part["text"])
        if calls:
            delta["tool_calls"] = calls
        reason = candidate.get("finishReason")
        finish = None
        if reason or (_blocked(payload) and not candidate):
            finish = "content_filter" if not reason else _finish_reason(reason, self._tool_index >= 0)
        if not delta and finish is None:
            return []
        chunk: Chunk = {
            "id": self._id,
            "object": "chat.completion.chunk",
            "model": self._model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        usage = payload.get("usageMetadata")
        if finish is not None and isinstance(usage, Mapping):
            chunk["usage"] = _usage(usage)
        return [chunk]

    def finish(self) -> list[Chunk]:
        return []


def decoder(route: Route) -> StreamDecoder:
    return GeminiStreamDecoder(route.profile.id, route.model)
