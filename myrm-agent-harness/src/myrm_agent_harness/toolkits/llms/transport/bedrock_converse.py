"""Bedrock Converse wire: OpenAI-shaped input to ``POST /model/{id}/converse`` and ``/converse-stream``.

[INPUT]
- transport.profile (POS: Route — endpoint root, bare model id and the Bedrock API key)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest, RequestSigner)
- transport.bedrock_sigv4 (POS: AWS credential chain and the signature of a request)
- transport.bedrock_content (POS: messages as Converse turns, tool name escape)
- transport.bedrock_structured (POS: structured output, native or as a synthetic tool)
- transport.json_schema (POS: reference inlining of tool schemas)
- transport.anthropic_thinking (POS: thinking block and effort of a request)
- transport.capabilities (POS: what the model accepts)

[OUTPUT]
- prepare: a PreparedRequest for the Converse (or ConverseStream) operation

[POS]
Request half of the Bedrock wire (answers are read by ``bedrock_response``). A Bedrock API key is sent as a bearer
token; without one the request is signed with the AWS credential chain (``bedrock_sigv4``), which needs botocore (extra
``bedrock``) and may block, so ``prepare`` is then run off the event loop. The region of the default endpoint comes from
the model ARN, the AWS region variables or, when signing, the region of the AWS profile. Converse is the one operation
spoken, so ``converse/`` and ``invoke/`` route prefixes of a model id are dropped. The caller's tools and tool choice
are sent as stated, whichever model it is: the catalog can lag a model's real abilities, and a refusal from the API says
so plainly. Reasoning is asked for the way each model family takes it: a thinking block for Claude, ``reasoningConfig``
for Nova 2, ``reasoning_effort`` for gpt-oss, all in ``additionalModelRequestFields``; a model without reasoning is sent
none. Where the catalog lists it, ``parallel_tool_calls`` becomes Anthropic's ``disable_parallel_tool_use`` there as
well. A request that replays tool calls but declares no tools gets a placeholder tool, which the API demands. A tool
choice the caller states wins over the forced call of the synthetic structured-output tool.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from typing import Final
from urllib.parse import quote

from myrm_agent_harness.toolkits.llms.catalog import model_facts
from myrm_agent_harness.toolkits.llms.transport.anthropic_thinking import Thinking, request_thinking
from myrm_agent_harness.toolkits.llms.transport.bedrock_content import (
    Block,
    Turn,
    cache_point,
    encode_tool_name,
    to_turns,
)
from myrm_agent_harness.toolkits.llms.transport.bedrock_sigv4 import load_credentials, request_signer
from myrm_agent_harness.toolkits.llms.transport.bedrock_structured import (
    JSON_TOOL,
    json_tool,
    output_config,
    structured,
    supports_native_output,
)
from myrm_agent_harness.toolkits.llms.transport.capabilities import claude_traits
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, RequestSigner
from myrm_agent_harness.toolkits.llms.transport.json_schema import inline_refs
from myrm_agent_harness.toolkits.llms.transport.params import CallOptions, merge_headers, split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

logger = logging.getLogger(__name__)

_ENDPOINT: Final = "https://bedrock-runtime.{region}.amazonaws.com"
_REGION_ENV: Final = ("AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION")
_DEFAULT_REGION: Final = "us-west-2"
_ARN_REGION: Final = re.compile(r"^arn:aws[\w-]*:bedrock:([a-z0-9-]+):")
# ARNs whose last segment is an opaque id: nothing in them says which model answers.
_OPAQUE_ARN: Final = re.compile(
    r"^arn:aws[\w-]*:bedrock:[a-z0-9-]*:\d*:(?:application-inference-profile|provisioned-model)/"
)
# ``bedrock/converse/<id>`` and ``bedrock/invoke/<id>`` name the same model; this wire speaks Converse for both.
_OPERATION_PREFIX: Final = re.compile(r"^(?:converse|invoke)/")
# Cross-region inference profiles prefix the model id (``us.meta.llama3-3-70b-instruct-v1:0``).
_PROFILE_REGIONS: Final = frozenset({"global", "us", "eu", "apac", "jp", "au", "us-gov"})
_JSON_ROOT_TYPES: Final = frozenset({"array", "boolean", "integer", "null", "number", "object", "string"})
_EFFORTS: Final = frozenset({"low", "medium", "high"})
_EMPTY_SCHEMA: Final[dict[str, object]] = {"type": "object", "properties": {}}
_PLACEHOLDER_TOOL: Final[Block] = {
    "toolSpec": {
        "name": "dummy_tool",
        "description": "This is a dummy tool call",
        "inputSchema": {"json": {**_EMPTY_SCHEMA, "required": []}},
    }
}


# --- tools -----------------------------------------------------------------------------------------------------


def _described(description: object, name: str) -> str:
    """The API rejects a blank description, so a tool without a real one is described by its name."""
    return description if isinstance(description, str) and description.strip() else name


def _tool_specs(raw: object, model: str) -> list[Block]:
    specs: list[Block] = []
    for tool in raw if isinstance(raw, list) else []:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if not isinstance(function, Mapping) or not function.get("name"):
            continue
        parameters = function.get("parameters")
        schema = inline_refs(parameters) if isinstance(parameters, Mapping) else dict(_EMPTY_SCHEMA)
        if schema.get("type") not in _JSON_ROOT_TYPES:
            schema["type"] = "object"
        name = encode_tool_name(str(function["name"]))
        spec = {
            "name": name,
            "description": _described(function.get("description"), name),
            "inputSchema": {"json": schema},
        }
        specs.append({"toolSpec": spec})
        specs.extend(cache_point(function, model) or cache_point(tool, model))
    return specs


def _base_model(model: str) -> str:
    """The model id without its inference-profile ARN path and cross-region prefix."""
    name = model.rsplit("/", 1)[-1] if model.startswith("arn:") else model
    prefix, dot, rest = name.partition(".")
    return rest if dot and prefix in _PROFILE_REGIONS else name


def _caller_tools(params: Mapping[str, object], model: str) -> list[Block]:
    """The tools a call offers: its own unless it declines them, and Nova's grounding."""
    specs = [] if params.get("tool_choice") == "none" else _tool_specs(params.get("tools"), model)
    if "nova" in model.lower() and isinstance(params.get("web_search_options"), Mapping):
        specs.append({"systemTool": {"name": "nova_grounding"}})
    return specs


def _forces_tool(model: str) -> bool:
    """Whether the model is known to take a forced ``toolChoice``: Claude does, the others as the catalog states."""
    return (
        "claude" in model.lower() or (model_facts(model, "bedrock_converse") or {}).get("supports_tool_choice") is True
    )


def _tool_choice(choice: object, *, may_force: bool) -> Block | None:
    """Converse's ``toolChoice`` for an OpenAI ``tool_choice``; without ``may_force`` a demanded call stays automatic."""
    if choice == "auto":
        return {"auto": {}}
    if choice in ("required", "any"):
        return {"any": {}} if may_force else {"auto": {}}
    if isinstance(choice, Mapping):
        function = choice.get("function")
        name = function.get("name") if isinstance(function, Mapping) else choice.get("name")
        if name:
            # The tool spec carries the escaped name, so the choice has to name the same string.
            return {"tool": {"name": encode_tool_name(str(name))}} if may_force else {"auto": {}}
    return None


def _anthropic_view(turns: Sequence[Turn]) -> list[dict[str, object]]:
    """The turns as ``anthropic_thinking`` reads them: which assistant turn calls tools, which opens with thinking,
    and which user turn answers tool calls."""
    kinds = {"reasoningContent": "thinking", "toolUse": "tool_use", "toolResult": "tool_result"}
    return [
        {"role": role, "content": [{"type": next((v for k, v in kinds.items() if k in b), "text")} for b in blocks]}
        for role, blocks in turns
    ]


def _holds_tool_blocks(turns: Sequence[Turn]) -> bool:
    return any("toolUse" in b or "toolResult" in b for _, blocks in turns for b in blocks)


# --- request ---------------------------------------------------------------------------------------------------


def _claude_like(model: str) -> bool:
    """Whether Claude's request rules apply: Claude by name, or a model that hides behind an opaque ARN.

    An application inference profile or provisioned model is most often Claude, and a rule the model refuses is
    refused with a message that names it, while a thinking block or the sampling rules silently withheld would not be.
    """
    return "claude" in model.lower() or _OPAQUE_ARN.match(model) is not None


def _reasoning(model: str, params: Mapping[str, object], thinking: Thinking, *, claude: bool) -> dict[str, object]:
    """The ``additionalModelRequestFields`` entries that switch reasoning on, as the model family takes them."""
    raw = params.get("reasoning_effort")
    effort = raw.lower() if isinstance(raw, str) else None
    name = model.lower()
    if claude:
        fields: dict[str, object] = {}
        if thinking.block is not None:
            fields["thinking"] = thinking.block
        if thinking.effort is not None:
            fields["output_config"] = {"effort": thinking.effort}
        return fields
    if "amazon.nova-2-" in name and effort in _EFFORTS:
        return {"reasoningConfig": {"type": "enabled", "maxReasoningEffort": effort}}
    if "gpt-oss" in name and effort in _EFFORTS:
        return {"reasoning_effort": effort}
    return {}


def _top_k(model: str, params: Mapping[str, object], *, claude: bool, sampling: bool) -> dict[str, object]:
    """``top_k`` where the model takes one: Claude's own field and Nova's ``inferenceConfig.topK``."""
    top_k = params.get("top_k")
    if not sampling or not isinstance(top_k, int) or isinstance(top_k, bool):
        return {}
    if claude:
        return {"top_k": top_k}
    return {"inferenceConfig": {"topK": top_k}} if _base_model(model).startswith("amazon.nova") else {}


def _parallel_tool_use(
    model: str, params: Mapping[str, object], existing: object, *, has_choice: bool
) -> dict[str, object]:
    """Anthropic's ``disable_parallel_tool_use`` where Converse takes it: the models the catalog lists for it.

    Merged into any ``tool_choice`` entry the caller already put in the model fields. The ``type`` key is Converse's
    own business once ``toolConfig.toolChoice`` is sent, and the API refuses the two together.
    """
    parallel = params.get("parallel_tool_calls")
    listed = any(
        (model_facts(candidate, "bedrock_converse") or {}).get("supports_parallel_tool_use_config") is True
        for candidate in (model, _base_model(model))
    )
    if not isinstance(parallel, bool) or not listed:
        return {}
    merged = {
        "type": "auto",
        **(existing if isinstance(existing, Mapping) else {}),
        "disable_parallel_tool_use": not parallel,
    }
    if has_choice:
        merged.pop("type", None)
    return {"tool_choice": merged}


def _inference_config(params: Mapping[str, object], *, claude: bool, sampling: bool) -> dict[str, object]:
    config: dict[str, object] = {}
    max_tokens = params.get("max_completion_tokens") or params.get("max_tokens")
    if isinstance(max_tokens, int) and not isinstance(max_tokens, bool) and max_tokens > 0:
        config["maxTokens"] = max_tokens
    if sampling:
        if params.get("temperature") is not None:
            config["temperature"] = params["temperature"]
        # Current Claude models refuse temperature and top_p together; temperature is the one callers tune.
        if params.get("top_p") is not None and not (claude and "temperature" in config):
            config["topP"] = params["top_p"]
    stop = params.get("stop")
    sequences = [stop] if isinstance(stop, str) else stop if isinstance(stop, list) else []
    if kept := [s for s in sequences if isinstance(s, str) and s]:
        config["stopSequences"] = kept
    return config


def _body(model: str, messages: Sequence[Mapping[str, object]], opts: CallOptions) -> dict[str, object]:
    params = opts.body
    claude = _claude_like(model)
    traits = claude_traits(model)
    system, turns = to_turns(messages, model)
    thinking = request_thinking(params, traits, _anthropic_view(turns)) if claude else Thinking()
    thinking_on = thinking.block is not None and thinking.block.get("type") != "disabled"
    reasoning = _reasoning(model, params, thinking, claude=claude)
    # A budgeted thinking block and gpt-oss's reasoning effort are known to refuse a forced tool call; the other
    # reasoning modes are sent it as asked, and the API says so if it objects. A structured answer is only ever
    # offered, never forced, while any reasoning is on.
    budgeted = thinking.block is not None and thinking.block.get("type") == "enabled"
    refuses_forcing = budgeted or "reasoning_effort" in reasoning
    reasons = thinking_on or "reasoning_effort" in reasoning or "reasoningConfig" in reasoning
    # Extended thinking accepts only the default sampling, and the newest Claude generation none at all.
    sampling = not claude or (traits.sampling and not thinking_on)
    specs = _caller_tools(params, model)
    choice = _tool_choice(params.get("tool_choice"), may_force=not refuses_forcing)
    asked = structured(params.get("response_format"))
    native = asked is not None and supports_native_output(model)
    if asked is not None and not native:
        specs.insert(0, json_tool(asked))
        if choice is None and not reasons and _forces_tool(model):
            choice = {"tool": {"name": JSON_TOOL}}
    if not specs and _holds_tool_blocks(turns):
        specs = [_PLACEHOLDER_TOOL]
    body: dict[str, object] = {
        "messages": [{"role": role, "content": blocks} for role, blocks in turns],
        "inferenceConfig": _inference_config(params, claude=claude, sampling=sampling),
    }
    if system:
        body["system"] = system
    if specs:
        body["toolConfig"] = {"tools": specs, **({"toolChoice": choice} if choice is not None else {})}
    if asked is not None and native:
        body["outputConfig"] = output_config(asked)
    fields = {**reasoning, **_top_k(model, params, claude=claude, sampling=sampling), **opts.extra_body}
    fields.update(
        _parallel_tool_use(model, params, fields.get("tool_choice"), has_choice=bool(specs) and choice is not None)
    )
    if fields:
        body["additionalModelRequestFields"] = fields
    return body


def _region(model: str, profile_region: str | None = None) -> str:
    """The region of a call: the model ARN's, else the AWS variables', else the AWS profile's, else the default."""
    arn = _ARN_REGION.match(model)
    if arn:
        return arn[1]
    return next((v for name in _REGION_ENV if (v := os.environ.get(name))), None) or profile_region or _DEFAULT_REGION


def prepare(route: Route, messages: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> PreparedRequest:
    """Authenticated by the Bedrock API key when there is one; otherwise signed with the AWS credential chain.

    Resolving the chain can block (files, instance metadata, a token service), so a caller on the event loop runs
    this off it (see ``client.LLMTransport.acompletion``).
    """
    opts = split_params(params)
    model = _OPERATION_PREFIX.sub("", route.model)
    headers: dict[str, str] = {}
    signer: RequestSigner | None = None
    if route.api_key:
        headers["Authorization"] = f"Bearer {route.api_key}"
        region = _region(model)
    else:
        credentials = load_credentials()
        region = _region(model, credentials.region)
        signer = request_signer(credentials, region)
    endpoint = (route.base_url or _ENDPOINT).replace("{region}", region)
    operation = "converse-stream" if opts.stream else "converse"
    return PreparedRequest(
        provider=route.profile.id,
        url=f"{endpoint}/model/{quote(model, safe='')}/{operation}",
        headers=merge_headers(headers, opts.headers),
        body=_body(model, messages, opts),
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
        framing="eventstream",
        retries=DEFAULT_RETRIES,
        signer=signer,
    )
