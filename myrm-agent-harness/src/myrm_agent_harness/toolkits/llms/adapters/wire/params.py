"""Build Responses-wire request kwargs from TransportChatModel call params.

[INPUT]
- typing::Any (POS: Python 类型标注标准库)
- toolkits.llms.adapters.wire.translator::chat_messages_to_responses_input,
  extract_responses_instructions, resolve_min_output_tokens
  (POS: Responses wire 出站请求翻译层)

[OUTPUT]
- build_responses_kwargs: dict[str, Any] ready for the transport's Responses call,
  with system messages lifted into `instructions` and reasoning config normalized

[POS]
Request assembly for the Responses wire. Delegates message translation to translator.py
and strips trailing endpoint suffixes so callers may pass either a base URL or a full
endpoint. Harness-only authoring layer; vendor routing tables live in server `app/core/wire/`.
"""

from __future__ import annotations

from typing import Any

from myrm_agent_harness.toolkits.llms.adapters.wire.translator import (
    chat_messages_to_responses_input,
    extract_responses_instructions,
    resolve_min_output_tokens,
)


def _responses_tool_choice(choice: Any) -> Any:
    """Chat-completions ``{"type": "function", "function": {"name": ...}}`` in its flat Responses form."""
    function = choice.get("function") if isinstance(choice, dict) else None
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return {"type": "function", "name": function["name"]}
    return choice


def _responses_text_format(response_format: Any) -> dict[str, Any] | None:
    """Structured-output request in the Responses ``text.format`` shape; plain ``json_object`` maps one to one."""
    if not isinstance(response_format, dict):
        return None
    kind = response_format.get("type")
    if kind == "json_object":
        return {"type": "json_object"}
    spec = response_format.get("json_schema")
    if kind != "json_schema" or not isinstance(spec, dict) or not isinstance(spec.get("schema"), dict):
        return None
    return {
        "type": "json_schema",
        "name": str(spec.get("name") or "response"),
        "schema": spec["schema"],
        "strict": bool(spec.get("strict", False)),
    }


def build_responses_kwargs(
    message_dicts: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Translate chat completion params into Responses API kwargs."""
    instructions, remaining = extract_responses_instructions(message_dicts)
    responses_input = chat_messages_to_responses_input(remaining)

    requested_max = params.get("max_output_tokens") or params.get("max_tokens")
    max_output = resolve_min_output_tokens(int(requested_max) if isinstance(requested_max, int) else None)

    raw_extra_body = params.get("extra_body")
    extra_body: dict[str, Any] = raw_extra_body if isinstance(raw_extra_body, dict) else {}
    reasoning = extra_body.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning_effort = params.get("reasoning_effort") or extra_body.get("reasoning_effort")
        if reasoning_effort is not None:
            reasoning = {"effort": str(reasoning_effort)}

    api_base = params.get("api_base")
    if isinstance(api_base, str):
        api_base = api_base.rstrip("/")
        if api_base.endswith("/responses"):
            api_base = api_base[: -len("/responses")]
        elif api_base.endswith("/chat/completions"):
            api_base = api_base[: -len("/chat/completions")]

    kwargs: dict[str, Any] = {
        "model": params.get("model"),
        "input": responses_input,
        "max_output_tokens": max_output,
        "api_key": params.get("api_key"),
        "api_base": api_base,
        "stream": bool(params.get("stream")),
    }
    if instructions:
        kwargs["instructions"] = instructions
    if reasoning:
        kwargs["reasoning"] = reasoning
    include = extra_body.get("include")
    if isinstance(include, list) and include:
        kwargs["include"] = include
    if params.get("tools"):
        kwargs["tools"] = params["tools"]
    if params.get("tool_choice") is not None:
        kwargs["tool_choice"] = _responses_tool_choice(params["tool_choice"])
    if params.get("parallel_tool_calls") is not None:
        kwargs["parallel_tool_calls"] = params["parallel_tool_calls"]
    if isinstance(params.get("web_search_options"), dict):
        kwargs["web_search_options"] = params["web_search_options"]
    if (text_format := _responses_text_format(params.get("response_format"))) is not None:
        kwargs["text"] = {"format": text_format}
    if params.get("temperature") is not None:
        kwargs["temperature"] = params["temperature"]
    if params.get("top_p") is not None:
        kwargs["top_p"] = params["top_p"]
    if params.get("timeout") is not None:
        kwargs["timeout"] = params["timeout"]
    extra_headers = params.get("extra_headers")
    if isinstance(extra_headers, dict):
        kwargs["extra_headers"] = extra_headers
    return kwargs
