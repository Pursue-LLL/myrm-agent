"""Model capabilities that decide how a request body is shaped.

[INPUT]
- catalog::model_facts (POS: capability flags and output ceiling of a model)

[OUTPUT]
- ClaudeTraits / claude_traits: what the Anthropic Messages API accepts from one Claude model
- claude_version: the (major, minor) generation a Claude model id names, for rules that start at one generation
- keeps_temperature_without_reasoning: whether an OpenAI reasoning model takes a temperature while it does not reason
- gemini_from_3 / gemini_thinks_by_level / gemini_thinking_level: which Gemini generation a model id belongs to and how
  it takes thinking

[POS]
The wires are pure translations of one call; the few request rules that depend on the model rather than on the
protocol live here, so a wire asks one question instead of owning a model table. The catalog states each fact for the
models it lists; a model it does not list (a release newer than the snapshot, a dated alias) is classified by its
name, so a new Claude generation works before the next catalog sync. A catalog flag the entry does not state falls
back to the same name rule. Gemini has no catalog flag for these rules: the generation number in the id decides, as a
version gate rather than a ``gemini-3`` prefix, so a later generation is never mistaken for a legacy one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from myrm_agent_harness.toolkits.llms.catalog import model_facts

# Snapshot dates (``claude-opus-4-20250514``) are not minor versions: a minor is one or two digits followed by a separator.
_CLAUDE_VERSION: Final = re.compile(
    r"claude[-_.](opus|sonnet|haiku|fable|mythos)[-_.](\d+)(?:[-_.](\d{1,2})(?=$|[-_.@:]))?", re.IGNORECASE
)
_NAMED_FAMILIES: Final = frozenset({"fable", "mythos"})
# First version of each family that thinks adaptively (``thinking.type: adaptive``) instead of by a token budget.
_ADAPTIVE_FROM: Final = {"opus": (4, 6), "sonnet": (4, 6), "haiku": (5, 5)}
_NO_SAMPLING_FROM: Final = (4, 7)
_XHIGH_FROM: Final = (4, 7)
_GEMINI_VERSION: Final = re.compile(r"gemini-(\d+)(?:\.(\d+))?", re.IGNORECASE)
# ``gemini-flash-latest`` and the like: Google moves them to the newest release of each variant.
_GEMINI_ALIAS: Final = re.compile(r"^(?:models/)?gemini-.*-latest$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ClaudeTraits:
    """What the Messages API takes from one Claude model; the defaults describe a legacy model."""

    # temperature, top_p and top_k are accepted; the newest generation answers 400 to any of them.
    sampling: bool = True
    # ``thinking: {"type": "adaptive"}`` steered by ``output_config.effort``; token budgets are deprecated or refused.
    adaptive_thinking: bool = False
    # ``output_config.effort`` levels beyond ``high``.
    xhigh_effort: bool = False
    max_effort: bool = False
    # The model's output ceiling: the answer budget when the caller states none.
    max_output_tokens: int | None = None


def _flag(info: Mapping[str, object], name: str, fallback: bool) -> bool:
    stated = info.get(name)
    return stated if isinstance(stated, bool) else fallback


def _by_name(model: str) -> ClaudeTraits:
    match = _CLAUDE_VERSION.search(model)
    if match is None:  # Claude 3 ids put the family after the version; every other model is not Claude
        return ClaudeTraits()
    family = match[1].lower()
    version = (int(match[2]), int(match[3] or 0))
    named = family in _NAMED_FAMILIES
    adaptive = named or version >= _ADAPTIVE_FROM[family]
    return ClaudeTraits(
        sampling=not (named or version >= _NO_SAMPLING_FROM),
        adaptive_thinking=adaptive,
        xhigh_effort=adaptive and (named or version >= _XHIGH_FROM),
        max_effort=adaptive,
    )


def claude_version(model: str) -> tuple[int, int] | None:
    """``(major, minor)`` of a Claude id that states them after the family (``claude-sonnet-4-5``); else ``None``."""
    match = _CLAUDE_VERSION.search(model)
    return (int(match[2]), int(match[3] or 0)) if match else None


def _ceiling(info: Mapping[str, object]) -> int | None:
    for field in ("max_output_tokens", "max_tokens"):
        value = info.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def claude_traits(model: str) -> ClaudeTraits:
    """Traits of ``model`` (a bare Claude id; any other id gets the legacy defaults)."""
    info = model_facts(model, "anthropic") or {}
    named = _by_name(model)
    return ClaudeTraits(
        sampling=_flag(info, "supports_sampling_params", named.sampling),
        adaptive_thinking=_flag(info, "supports_adaptive_thinking", named.adaptive_thinking),
        xhigh_effort=_flag(info, "supports_xhigh_reasoning_effort", named.xhigh_effort),
        max_effort=_flag(info, "supports_max_reasoning_effort", named.max_effort),
        max_output_tokens=_ceiling(info),
    )


def keeps_temperature_without_reasoning(model: str) -> bool:
    """Whether ``model`` takes any temperature while its reasoning effort is ``none`` (GPT-5.1 and later)."""
    return bool((model_facts(model, "openai") or {}).get("supports_none_reasoning_effort") is True)


def _gemini_version(model: str) -> tuple[int, int] | None:
    match = _GEMINI_VERSION.search(model)
    return (int(match[1]), int(match[2] or 0)) if match else None


def gemini_from_3(model: str) -> bool:
    """Whether ``model`` is Gemini 3 or a later generation.

    Those take a call id and a ``thoughtSignature`` on every function call of a replayed history and accept inline
    media inside a function response; Gemini 2.x rejects the id and takes the media beside the response.
    """
    version = _gemini_version(model)
    return version is not None and version[0] >= 3


def gemini_thinks_by_level(model: str) -> bool:
    """Whether ``model`` takes ``thinkingLevel`` instead of a token budget: Gemini 3 and later, and the ``-latest`` aliases."""
    return gemini_from_3(model) or _GEMINI_ALIAS.match(model) is not None


def gemini_thinking_level(model: str, effort: str) -> str:
    """The ``thinkingLevel`` a reasoning effort asks of a model that thinks by level.

    Flash takes minimal, low, medium and high; Pro only low and high, plus medium from 3.1 on. An effort the model has
    no level for becomes the nearest one it has, and Gemini has nothing above ``high``.
    """
    flash = "flash" in model.lower()
    version = _gemini_version(model)
    has_medium = flash or (version is not None and version >= (3, 1))
    if effort == "minimal":
        return "minimal" if flash else "low"
    if effort == "low":
        return "low"
    if effort == "medium":
        return "medium" if has_medium else "high"
    return "high"
