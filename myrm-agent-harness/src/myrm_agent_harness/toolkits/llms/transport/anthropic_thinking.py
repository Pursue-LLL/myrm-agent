"""How an Anthropic Messages request asks for reasoning.

[INPUT]
- transport.capabilities (POS: ClaudeTraits — adaptive thinking and effort levels of the model)

[OUTPUT]
- Thinking / request_thinking: the ``thinking`` block and ``output_config.effort`` one request carries

[POS]
Request half of extended thinking for the Anthropic wire. A generation that thinks adaptively takes
``thinking: {"type": "adaptive"}`` steered by ``output_config.effort``; every earlier one takes a token budget. The
level the caller names is clamped to what the model offers, because an unsupported effort is a 400. Thinking is
switched off for a request in the middle of a tool loop whose tool-calling turns carry no signed thinking block,
because the API rejects such a replay; turns before the user's latest message are not judged.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Final, NamedTuple

from myrm_agent_harness.toolkits.llms.transport.capabilities import ClaudeTraits

logger = logging.getLogger(__name__)

_THINKING_TYPES: Final = ("thinking", "redacted_thinking")
_BUDGET: Final = {"minimal": 1024, "low": 1024, "medium": 2048, "high": 4096, "xhigh": 8192, "max": 8192}
_EFFORT: Final = {"minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}
_DISABLED: Final = frozenset({"none", "off", "disable", "disabled"})


class Thinking(NamedTuple):
    block: dict[str, object] | None = None
    effort: str | None = None


def _clamp_effort(effort: str, traits: ClaudeTraits) -> str:
    """The highest level at or below ``effort`` the model offers."""
    if effort == "xhigh" and not traits.xhigh_effort:
        effort = "max"
    if effort == "max" and not traits.max_effort:
        effort = "high"
    return effort


def _answers_tool_calls(turn: Mapping[str, object]) -> bool:
    blocks = turn.get("content")
    return isinstance(blocks, list) and any(isinstance(b, Mapping) and b.get("type") == "tool_result" for b in blocks)


def _tool_loop(turns: Sequence[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
    """The turns of the tool loop in progress: those after the user's latest message that is not just tool results."""
    for position in range(len(turns) - 1, -1, -1):
        if turns[position].get("role") == "user" and not _answers_tool_calls(turns[position]):
            return turns[position + 1 :]
    return turns


def _lacks_replay(turns: Sequence[Mapping[str, object]]) -> bool:
    """Whether a turn of the tool loop in progress calls tools without the thinking block the API demands first.

    Earlier conversation turns are not judged: the API takes them with or without their reasoning, so history that was
    pruned at a turn boundary does not switch thinking off.
    """
    for turn in _tool_loop(turns):
        blocks = turn.get("content")
        if turn.get("role") != "assistant" or not isinstance(blocks, list):
            continue
        calls_tool = any(isinstance(b, Mapping) and b.get("type") == "tool_use" for b in blocks)
        leads = bool(blocks) and isinstance(blocks[0], Mapping) and blocks[0].get("type") in _THINKING_TYPES
        if calls_tool and not leads:
            return True
    return False


def _requested(params: Mapping[str, object], traits: ClaudeTraits) -> Thinking:
    explicit = params.get("thinking")
    if isinstance(explicit, Mapping):
        return Thinking(dict(explicit))
    effort = params.get("reasoning_effort")
    if not isinstance(effort, str) or effort.lower() in _DISABLED:
        return Thinking()
    level = effort.lower()
    if traits.adaptive_thinking:
        mapped = _EFFORT.get(level)
        return Thinking({"type": "adaptive"}, _clamp_effort(mapped, traits)) if mapped else Thinking()
    budget = _BUDGET.get(level)
    return Thinking({"type": "enabled", "budget_tokens": budget}) if budget else Thinking()


def request_thinking(
    params: Mapping[str, object], traits: ClaudeTraits, turns: Sequence[Mapping[str, object]]
) -> Thinking:
    """The thinking block and effort for a call: the caller's explicit ``thinking`` or one derived from its effort."""
    thinking = _requested(params, traits)
    if thinking.block is not None and _lacks_replay(turns):
        logger.info("Thinking is off for this turn: earlier tool calls carry no signed thinking block to replay")
        return Thinking(None, thinking.effort)
    return thinking
