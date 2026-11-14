"""Registry of every intentional difference between the baseline client library's Bedrock requests and the transport's.

[INPUT]
- golden_allowed_types (POS: AllowedDiff, the shape of one registered difference)
- golden_matrix::BEDROCK_VARIANTS (POS: the Bedrock model families of the capture matrix)

[OUTPUT]
- BEDROCK_RULES: the registry for the Bedrock Converse wire

[POS]
Companion of ``golden_allowed`` for Bedrock, the provider the transport reaches through its own Converse wire. The
recorded Bedrock requests (the base model and fifteen model families, each through the scenarios that change what a
family is sent) agree with the transport's on every message, tool, tool choice, cache point, image and stream flag
except for what is listed here with the reason; the golden test fails on a difference that is not listed and on a
rule that matches nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from .golden_allowed_types import AllowedDiff
from .golden_matrix import BEDROCK_VARIANTS

_BEDROCK = ("bedrock", *BEDROCK_VARIANTS)
_CLAUDE = (
    "bedrock",
    "bedrock_claude35",
    "bedrock_claude37",
    "bedrock_claude45",
    "bedrock_haiku45",
    "bedrock_opus45",
    "bedrock_sonnet46",
    "bedrock_opus47",
)
# An application inference profile hides its model; the wire treats it as Claude, the baseline library did too.
_CLAUDE_LIKE = (*_CLAUDE, "bedrock_arn")
# Models that have no reasoning to switch on; the baseline library sent them a Claude thinking block regardless.
_UNREASONING = ("bedrock_nova", "bedrock_llama33", "bedrock_llama3", "bedrock_mistral", "bedrock_deepseek")
_NOT_CLAUDE = (*_UNREASONING, "bedrock_nova2", "bedrock_gptoss")
_REASONING = (
    "reasoning_high",
    "reasoning_tools",
    "reasoning_xhigh",
    "reasoning_medium",
    "reasoning_minimal",
    "reasoning_required",
    "json_schema_reasoning",
    "tools_json_reasoning",
)
# What the baseline library copied into additionalModelRequestFields without any model reading it.
_UNREAD = frozenset(
    {
        "extra_body",
        "max_tokens",
        "frequency_penalty",
        "seed",
        "stop",
        "reasoning_effort",
        "response_format",
        "stream_options",
    }
)
# The recording of these scenarios resolved its region from the AWS configuration of the recording machine
# (us-east-1); the `defaults` and `sampling` scenarios, recorded later without it, show the library's own fallback.
_RECORDED_WITH_MACHINE_REGION = (
    "basic",
    "cache_control",
    "extra_body",
    "headers",
    "image",
    "json_schema",
    "reasoning_high",
    "reasoning_tools",
    "stream",
    "tool_history",
    "tools",
)
_SAFE_TOOL_USE_ID = re.compile(r"[A-Za-z0-9_-]+")


def _region_moved(diff: object) -> bool:
    return "bedrock-runtime.us-east-1" in str(getattr(diff, "old", "")) and "bedrock-runtime.us-west-2" in str(
        getattr(diff, "new", "")
    )


def _holds_only(extra: frozenset[str] = frozenset()) -> Callable[..., bool]:
    """Whether the removed ``additionalModelRequestFields`` object held nothing but unread copies (and ``extra``)."""
    allowed = _UNREAD | extra
    return lambda diff: isinstance(diff.old, Mapping) and set(diff.old) <= allowed


def _thinking_dropped(diff: object) -> bool:
    return str(getattr(diff, "path", "")).endswith("/thinking") or _holds_only(frozenset({"thinking"}))(diff)


def _id_made_safe(diff: object) -> bool:
    old, new = getattr(diff, "old", None), getattr(diff, "new", None)
    return (
        isinstance(old, str)
        and isinstance(new, str)
        and _SAFE_TOOL_USE_ID.fullmatch(old) is None
        and _SAFE_TOOL_USE_ID.fullmatch(new) is not None
    )


def _window_clamp(diff: object) -> bool:
    old, new = getattr(diff, "old", None), getattr(diff, "new", None)
    return isinstance(old, int) and isinstance(new, int) and new == 8192 and 0 < old < new


BEDROCK_RULES: tuple[AllowedDiff, ...] = (
    AllowedDiff(
        "bedrock-unread-model-fields",
        "The baseline library copied every parameter it had no field for into additionalModelRequestFields: the output "
        "limit a second time, stop words, seed and penalty, the whole extra_body object, stream options, the response "
        "format, the reasoning effort. No model reads them (Claude refuses unknown ones); the transport sends there "
        "only what a model takes.",
        "-",
        rf"/body/additionalModelRequestFields/({'|'.join(sorted(_UNREAD))})",
        providers=_BEDROCK,
    ),
    AllowedDiff(
        "bedrock-unread-model-fields-only",
        "The same copies, when they were all the object held: the transport sends no additionalModelRequestFields then.",
        "-",
        r"/body/additionalModelRequestFields",
        providers=_BEDROCK,
        when=_holds_only(),
    ),
    AllowedDiff(
        "bedrock-thinking-for-model-without-reasoning",
        "The baseline library turned a reasoning effort into a Claude thinking block for every model, Nova Pro, Llama, "
        "Mistral and DeepSeek R1 included. None of them takes a thinking block, and the API refuses the field; the "
        "transport sends reasoning only to the families that have it.",
        "-",
        r"/body/additionalModelRequestFields(/thinking)?",
        providers=_UNREASONING,
        scenarios=_REASONING,
        when=_thinking_dropped,
    ),
    AllowedDiff(
        "bedrock-extra-body-fields",
        "The caller's extra_body fields are additionalModelRequestFields entries; the baseline library nested them one "
        "level deeper, under an extra_body key no model reads.",
        "+",
        r"/body/additionalModelRequestFields/foo",
        providers=_BEDROCK,
        scenarios=("extra_body",),
    ),
    AllowedDiff(
        "bedrock-top-k",
        "top_k goes where the model takes it (Claude's own field, Nova's inferenceConfig.topK); the baseline library "
        "nested it under the extra_body key no model reads, so it never took effect.",
        "+",
        r"/body/additionalModelRequestFields/(top_k|inferenceConfig)",
        providers=_BEDROCK,
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "bedrock-model-refuses-sampling",
        "Claude Opus 4.7 takes no sampling parameter (the catalog flags it so); the baseline request sent a "
        "temperature to it.",
        "-",
        r"/body/inferenceConfig/temperature",
        providers=("bedrock_opus47",),
    ),
    AllowedDiff(
        "bedrock-thinking-after-completed-tool-turn",
        "Converse puts a short assistant turn between a tool result and the user text that follows it, so the last "
        "assistant turn calls no tool and asks for no thinking block; only a tool loop in progress makes the API demand "
        "one. The baseline library switched thinking off because an earlier assistant turn had called tools without a "
        "signed block.",
        "+",
        r"/body/additionalModelRequestFields/thinking",
        providers=_CLAUDE_LIKE,
        scenarios=("reasoning_tools",),
    ),
    AllowedDiff(
        "bedrock-thinking-default-temperature",
        "Extended thinking takes only the default temperature (the Anthropic wire drops it the same way); the baseline "
        "request sent 0.2 beside the thinking block.",
        "-",
        r"/body/inferenceConfig/temperature",
        providers=_CLAUDE_LIKE,
        scenarios=_REASONING,
    ),
    AllowedDiff(
        "bedrock-top-p-beside-temperature",
        "Only Claude takes just one of temperature and top_p; the baseline library dropped top_p from every Bedrock "
        "request that carried both, while Nova, Llama, Mistral, DeepSeek and gpt-oss accept the pair.",
        "+",
        r"/body/inferenceConfig/topP",
        providers=_NOT_CLAUDE,
        scenarios=("sampling",),
    ),
    AllowedDiff(
        "bedrock-tool-use-id-charset",
        "Converse accepts only letters, digits, underscore and hyphen in a toolUseId, so the ids of another provider "
        "('functions.get_weather:0') are rewritten, the call and its result alike; the baseline library sent them as "
        "they were.",
        "~",
        r"/body/messages\[\d+\]/content\[\d+\]/(toolUse|toolResult)/toolUseId",
        providers=_BEDROCK,
        scenarios=("tool_history_foreign_ids",),
        when=_id_made_safe,
    ),
    AllowedDiff(
        "bedrock-output-window-shared-with-input",
        "A model whose output limit equals its context window (Llama 3 70B: 8192 of 8192) had its maxTokens lowered by "
        "the baseline library to what the prompt left, counted with its own tokenizer; the transport sends the "
        "ceiling and leaves a request the window cannot hold to the provider's refusal.",
        "~",
        r"/body/inferenceConfig/maxTokens",
        providers=("bedrock_llama3",),
        scenarios=_REASONING,
        when=_window_clamp,
    ),
    AllowedDiff(
        "bedrock-forced-choice-beside-no-reasoning",
        "The baseline library demoted a forced tool call to automatic whenever a reasoning effort was set, because it "
        "had turned the effort into a thinking block. A model with no reasoning gets no block, so the call the caller "
        "demanded stays forced.",
        "+",
        r"/body/toolConfig/toolChoice/any",
        providers=_UNREASONING,
        scenarios=("reasoning_required",),
    ),
    AllowedDiff(
        "bedrock-forced-choice-beside-no-reasoning-auto",
        "The automatic choice the baseline library put there instead (see bedrock-forced-choice-beside-no-reasoning).",
        "-",
        r"/body/toolConfig/toolChoice/auto",
        providers=_UNREASONING,
        scenarios=("reasoning_required",),
    ),
    AllowedDiff(
        "bedrock-structured-tool-forced-beside-no-reasoning",
        "The baseline library left the synthetic structured-output tool unforced whenever a reasoning effort was set, "
        "for the same reason (see bedrock-forced-choice-beside-no-reasoning); a model with no reasoning is made to call "
        "it, as it is without the effort.",
        "+",
        r"/body/toolConfig/toolChoice",
        providers=_UNREASONING,
        scenarios=("json_schema_reasoning",),
    ),
    AllowedDiff(
        "bedrock-xhigh-unsupported-model",
        "Claude Sonnet 4.6 has no `xhigh` effort: the baseline library refused the call before sending anything; the "
        "wire sends the highest level the model has (`max`).",
        "count",
        r"",
        providers=("bedrock_sonnet46",),
        scenarios=("reasoning_xhigh",),
    ),
    AllowedDiff(
        "bedrock-fallback-region",
        "Without a region in the model id or the AWS variables both fall back to us-west-2; the baseline's first "
        "recording took us-east-1 from the AWS configuration of the machine it ran on, which the transport does not read.",
        "~",
        r"/url",
        providers=_BEDROCK,
        scenarios=_RECORDED_WITH_MACHINE_REGION,
        when=_region_moved,
    ),
)
