"""The shape of a registered difference and what the registries of the request matrix share.

[INPUT]
- (none) Pure data and predicates.

[OUTPUT]
- AllowedDiff: one registered difference (provider, kind of change, field, reason)
- HIDDEN_FETCHES: URLs the baseline library called on its own, outside the model call itself
- ANTHROPIC, GEMINI, GEMINI_2, GEMINI_3, NATIVE_SEARCH_CLAUDE: capture-matrix provider keys grouped by model family
- contains, only_repair_turns, media_moved_beside: predicates over one difference

[POS]
One definition of a registered difference for the request registry (``golden_allowed``), its three sections, and the
Bedrock and service companions, so a rule is written the same way wherever it is registered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

# Calls the baseline library made by itself while serving a model call (tokenizer downloads from a model hub,
# a configuration file fetched from a code-hosting site, Ollama's model-info lookup around an embedding call).
# The transport makes none of them. Matched as substrings of the request URL.
HIDDEN_FETCHES = ("huggingface.co", "raw.githubusercontent.com", "/api/show")

GEMINI_2 = ("gemini", "gemini_like", "gemini25pro", "gemini25flashlite")
GEMINI_3 = ("gemini3", "gemini31", "gemini3flash")
GEMINI = (*GEMINI_2, *GEMINI_3)
ANTHROPIC = (
    "anthropic",
    "anthropic_like",
    "anthropic_opus45",
    "anthropic_sonnet46",
    "anthropic_opus47",
    "anthropic_haiku45",
)
# Claude generations whose catalog entry flags the native web search tool (the baseline library's map did not).
NATIVE_SEARCH_CLAUDE = ("anthropic_sonnet46", "anthropic_opus47")


@dataclass(frozen=True, slots=True)
class AllowedDiff:
    id: str
    reason: str
    kind: str
    path: str  # regular expression matched against the whole field path
    providers: tuple[str, ...] | None = None
    scenarios: tuple[str, ...] | None = None
    when: Callable[..., bool] | None = None


def contains(side: str, text: str) -> Callable[..., bool]:
    return lambda diff: text in str(getattr(diff, side))


class _Change(Protocol):
    old: object
    new: object


def only_repair_turns(diff: _Change) -> bool:
    """Whether the current Gemini turns are the baseline's plus the model turns that keep a tool result and the user
    message after it apart (both sides arrive canonical: adjacent turns of one role already merged)."""
    if not isinstance(diff.new, list) or not isinstance(diff.old, list):
        return False
    placeholder = [{"text": "[The previous response was interrupted before it completed.]"}]
    kept: list[dict[str, object]] = []
    for turn in diff.new:
        if turn["parts"] == placeholder:
            continue
        if kept and kept[-1]["role"] == turn["role"]:
            kept[-1] = {**turn, "parts": [*kept[-1]["parts"], *turn["parts"]]}  # type: ignore[misc]
        else:
            kept.append(turn)
    return kept == diff.old


def media_moved_beside(diff: _Change) -> bool:
    """Whether the current Gemini parts are the baseline's with the media nested in each function response moved out
    to parts beside it."""
    if not isinstance(diff.new, list) or not isinstance(diff.old, list):
        return False
    moved: list[dict[str, object]] = []
    for part in diff.old:
        response = part.get("functionResponse")
        if not isinstance(response, dict) or "parts" not in response:
            moved.append(part)
            continue
        moved.append({"functionResponse": {key: value for key, value in response.items() if key != "parts"}})
        moved.extend(response["parts"])
    return moved == diff.new
