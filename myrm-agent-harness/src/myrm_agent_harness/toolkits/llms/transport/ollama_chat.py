"""Ollama chat wire: OpenAI-shaped input to ``/api/chat`` and back.

[INPUT]
- transport.profile (POS: Route — endpoint root and optional credential for hosted Ollama)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest, StreamDecoder; NDJSON framing)

[OUTPUT]
- prepare: a PreparedRequest for ``POST {base}/api/chat``
- parse: an Ollama chat answer as a chat.completion dict (content, thinking, tool_calls, usage)
- decoder: the NDJSON decoder yielding chat.completion.chunk dicts

[POS]
Native Ollama chat endpoint, the one that carries tools, structured output and thinking (the legacy
``/api/generate`` endpoint takes a flattened prompt and supports none of them). Sampling parameters live under
``options`` and are deep-merged with the ``options`` the model factory supplies (context window size).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.frames import json_frame
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, PreparedRequest, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.params import CallOptions, merge_headers, split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

logger = logging.getLogger(__name__)

_DATA_URL: Final = re.compile(r"^data:[^;,]+;base64,(?P<data>.+)$", re.DOTALL)
_DISABLED_EFFORT: Final = frozenset({"none", "off", "disable", "disabled"})
_LEVELED_THINKING: Final = re.compile(r"^gpt-oss", re.IGNORECASE)
_OPTION_NAMES: Final = (
    ("temperature", "temperature"),
    ("top_p", "top_p"),
    ("top_k", "top_k"),
    ("seed", "seed"),
    ("presence_penalty", "presence_penalty"),
    ("frequency_penalty", "frequency_penalty"),
)
Message = dict[str, object]


def _text_and_images(content: object) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return content, []
    texts: list[str] = []
    images: list[str] = []
    for part in content if isinstance(content, list) else []:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, Mapping) and part.get("type") == "text":
            texts.append(str(part.get("text") or ""))
        elif isinstance(part, Mapping) and part.get("type") == "image_url":
            image = part.get("image_url")
            url = image.get("url") if isinstance(image, Mapping) else image
            match = _DATA_URL.match(url) if isinstance(url, str) else None
            if match:
                images.append(match["data"])
            else:
                logger.warning("Dropping a remote image URL: Ollama accepts base64 image data only")
        elif isinstance(part, Mapping):
            logger.warning("Dropping content part of unsupported type %r for the Ollama API", part.get("type"))
    return "".join(texts), images


def _tool_calls(raw: object, names: dict[str, str]) -> list[Message]:
    calls: list[Message] = []
    for call in raw if isinstance(raw, list) else []:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        arguments = function.get("arguments")
        try:
            parsed = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else arguments
        except ValueError:
            parsed = {}
        name = str(function.get("name") or "")
        names[str(call.get("id") or "")] = name
        calls.append({"function": {"name": name, "arguments": parsed if isinstance(parsed, dict) else {}}})
    return calls


def _messages(messages: Sequence[Mapping[str, object]]) -> list[Message]:
    names: dict[str, str] = {}
    result: list[Message] = []
    for message in messages:
        role = str(message.get("role"))
        text, images = _text_and_images(message.get("content"))
        entry: Message = {"role": "system" if role == "developer" else role, "content": text}
        if images:
            entry["images"] = images
        if role == "assistant":
            calls = _tool_calls(message.get("tool_calls"), names)
            if calls:
                entry["tool_calls"] = calls
        elif role == "tool":
            tool_name = message.get("name") or names.get(str(message.get("tool_call_id") or ""))
            if tool_name:
                entry["tool_name"] = tool_name
        result.append(entry)
    return result


def _options(params: Mapping[str, object], extra: object) -> dict[str, object]:
    options: dict[str, object] = {}
    limit = params.get("max_completion_tokens") or params.get("max_tokens")
    if isinstance(limit, int) and limit > 0:
        options["num_predict"] = limit
    for source, target in _OPTION_NAMES:
        if params.get(source) is not None:
            options[target] = params[source]
    stop = params.get("stop")
    if isinstance(stop, str):
        options["stop"] = [stop]
    elif isinstance(stop, list) and stop:
        options["stop"] = stop
    if isinstance(extra, Mapping):
        options.update(extra)
    return options


def _think(model: str, effort: object) -> bool | str | None:
    if not isinstance(effort, str):
        return None
    if effort.lower() in _DISABLED_EFFORT:
        return False
    if _LEVELED_THINKING.match(model):
        return (
            "low"
            if effort.lower() in ("minimal", "low")
            else "high"
            if effort.lower() in ("high", "xhigh", "max")
            else "medium"
        )
    return True


def _format(response_format: object) -> object | None:
    if not isinstance(response_format, Mapping):
        return None
    if response_format.get("type") == "json_object":
        return "json"
    holder = response_format.get("json_schema")
    schema = holder.get("schema") if isinstance(holder, Mapping) else None
    return dict(schema) if response_format.get("type") == "json_schema" and isinstance(schema, Mapping) else None


def _body(route: Route, messages: Sequence[Mapping[str, object]], opts: CallOptions) -> dict[str, object]:
    params = opts.body
    extra = dict(opts.extra_body)
    body: dict[str, object] = {
        "model": route.model,
        "messages": _messages(messages),
        "stream": opts.stream,
    }
    options = _options(params, extra.pop("options", None))
    if options:
        body["options"] = options
    if params.get("tools"):
        body["tools"] = params["tools"]
    structured = _format(params.get("response_format"))
    if structured is not None:
        body["format"] = structured
    think = _think(route.model, params.get("reasoning_effort"))
    if think is not None:
        body["think"] = think
    body.update(extra)
    return body


def prepare(route: Route, messages: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> PreparedRequest:
    opts = split_params(params)
    if not route.base_url:
        raise UnsupportedProviderError("The Ollama wire needs an api_base")
    headers = {"Authorization": f"Bearer {route.api_key}"} if route.api_key else {}
    return PreparedRequest(
        provider=route.profile.id,
        url=f"{route.base_url}/api/chat",
        headers=merge_headers(headers, opts.headers),
        body=_body(route, messages, opts),
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
        framing="ndjson",
        retries=DEFAULT_RETRIES,
    )


# --- response --------------------------------------------------------------------------------------------------


def _calls_out(message: Mapping[str, object], first_index: int = 0) -> list[Message]:
    calls: list[Message] = []
    raw = message.get("tool_calls")
    for call in raw if isinstance(raw, list) else []:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        arguments = function.get("arguments")
        calls.append(
            {
                # Numbered by the calls kept, so a skipped entry leaves no gap for the next line to collide with.
                "index": first_index + len(calls),
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": function.get("name"),
                    "arguments": arguments
                    if isinstance(arguments, str)
                    else json.dumps(arguments or {}, ensure_ascii=False),
                },
            }
        )
    return calls


def _usage(payload: Mapping[str, object]) -> dict[str, object]:
    prompt, output = payload.get("prompt_eval_count"), payload.get("eval_count")
    prompt = prompt if isinstance(prompt, int) else 0
    output = output if isinstance(output, int) else 0
    return {"prompt_tokens": prompt, "completion_tokens": output, "total_tokens": prompt + output}


def _finish(payload: Mapping[str, object], has_tool_calls: bool) -> str:
    if has_tool_calls:
        return "tool_calls"
    return "length" if payload.get("done_reason") == "length" else "stop"


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("error"):
        raise LLMAnswerError(route.profile.id, payload)
    raw = payload.get("message")
    source: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    calls = _calls_out(source)
    message: Message = {"role": "assistant", "content": str(source.get("content") or "") or None}
    if source.get("thinking"):
        message["reasoning_content"] = source["thinking"]
    if calls:
        message["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in calls]
    return {
        "id": f"ollama-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": payload.get("model") or route.model,
        "choices": [{"index": 0, "message": message, "finish_reason": _finish(payload, bool(calls))}],
        "usage": _usage(payload),
    }


# --- stream ----------------------------------------------------------------------------------------------------


class OllamaStreamDecoder:
    """One NDJSON line is a message fragment; the line with ``done: true`` carries the counts and the end reason."""

    __slots__ = ("_id", "_model", "_provider", "_tool_calls", "done")

    def __init__(self, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._id = f"ollama-{uuid.uuid4().hex[:12]}"
        self._tool_calls = 0
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        payload = json_frame(self._provider, data)
        if payload is None:
            return []
        if payload.get("error"):
            raise LLMAnswerError(self._provider, payload, stream=True)
        raw = payload.get("message")
        source: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
        delta: Message = {}
        if source.get("content"):
            delta["content"] = source["content"]
        if source.get("thinking"):
            delta["reasoning_content"] = source["thinking"]
        calls = _calls_out(source, self._tool_calls)
        if calls:
            self._tool_calls += len(calls)
            delta["tool_calls"] = calls
        finished = payload.get("done") is True
        self.done = finished
        if not delta and not finished:
            return []
        chunk: Chunk = {
            "id": self._id,
            "object": "chat.completion.chunk",
            "model": payload.get("model") or self._model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": _finish(payload, self._tool_calls > 0) if finished else None,
                }
            ],
        }
        if finished:
            chunk["usage"] = _usage(payload)
        return [chunk]

    def finish(self) -> list[Chunk]:
        return []


def decoder(route: Route) -> StreamDecoder:
    return OllamaStreamDecoder(route.profile.id, route.model)
