"""Architecture gate: token budget of the static part of the first system message.

``messages[0]`` of an Agent turn starts with the server core prompt, followed by harness blocks
(datetime rules, agent core rules, channel output hint). Those parts are pure functions of
(surface, locale, channel), so their size is pinned here without any model call. The surfaces are the
general agent and the two search depths (quick and deep).

Every cap is the size measured after the last deliberate prompt change plus 5%. A change that adds text
must raise the cap in the same PR and say why, so the first turn cannot grow unnoticed.

Left out on purpose: the host environment line (it varies per host, so prompt text does not decide it). The
session canary and the security boundary rules are separate system messages behind the user's input, not part
of ``messages[0]``.
"""

from __future__ import annotations

import pytest
import tiktoken
from myrm_agent_harness.agent.streaming.agent_core_rules import AGENT_CORE_RULES
from myrm_agent_harness.agent.streaming.channel_output_hints import resolve_channel_output_hint
from myrm_agent_harness.agent.streaming.utils import DATETIME_SYSTEM_RULES
from myrm_agent_harness.utils.locale import is_chinese

from app.ai_agents.agent_middlewares.widget_capability_middleware import WIDGET_CAPABILITY_PROMPT
from app.ai_agents.prompts.general_agent_prompt import SEARCH_DEEP_SUFFIX, SEARCH_DEEP_SUFFIX_ZH, get_core_system_prompt

# o200k_base is the harness planning encoding (the same for every model).
# Measured per (surface, locale); cap = measured * 1.05 rounded up.
_ENCODING_NAME = "o200k_base"
_STATIC_FIRST_MESSAGE_CAPS: dict[tuple[str, str], int] = {
    ("full", "zh-CN"): 1293,
    ("full", "en"): 1098,
    ("search-normal", "zh-CN"): 2391,
    ("search-normal", "en"): 1646,
    ("search-deep", "zh-CN"): 2529,
    ("search-deep", "en"): 1763,
}
# Measured 348 tokens; the block rides in every web turn. Cap = measured * 1.05 rounded up.
_WIDGET_CAPABILITY_CAP = 366

# Section tags that prove each surface was assembled from the real blocks, not from an empty stand-in.
_SEARCH_MARKERS = ("<identity>", "<response_rules>", "<external_sources_citation_rules>")
_HARNESS_MARKERS = ("<datetime_rules>", "<agent_behavior_rules>", "[Output Format]")
_MARKERS_BY_SURFACE: dict[str, tuple[str, ...]] = {
    "full": ("<identity>", "<response_rules>", "<task_integrity>", *_HARNESS_MARKERS),
    "search-normal": (*_SEARCH_MARKERS, *_HARNESS_MARKERS),
    "search-deep": (*_SEARCH_MARKERS, "<deep_search_mode>", *_HARNESS_MARKERS),
}


def _token_count(text: str) -> int:
    return len(tiktoken.get_encoding(_ENCODING_NAME).encode(text, disallowed_special=()))


def _static_first_message(surface: str, locale: str) -> str:
    """Assemble the static blocks in the order the agent appends them to the system prompt."""
    if surface == "full":
        core = get_core_system_prompt("full", enable_answer_tool=False, locale=locale)
    else:
        core = get_core_system_prompt("search", locale=locale)
        if surface == "search-deep":
            core += SEARCH_DEEP_SUFFIX_ZH if is_chinese(locale) else SEARCH_DEEP_SUFFIX
    return core + DATETIME_SYSTEM_RULES + AGENT_CORE_RULES + resolve_channel_output_hint("web_chat")


class TestFirstTurnStaticPromptBudget:
    """CI gate: the static first system message and the widget capability block stay within their caps."""

    @pytest.mark.parametrize(("surface", "locale"), sorted(_STATIC_FIRST_MESSAGE_CAPS))
    def test_static_first_message_within_cap(self, surface: str, locale: str) -> None:
        cap = _STATIC_FIRST_MESSAGE_CAPS[(surface, locale)]
        tokens = _token_count(_static_first_message(surface, locale))
        assert tokens <= cap, (
            f"static first system message of {surface} for {locale} is {tokens} tokens, over the {cap} cap; "
            "trim the added text, or raise the cap in this PR and explain the cost and benefit"
        )

    def test_widget_capability_prompt_within_cap(self) -> None:
        tokens = _token_count(WIDGET_CAPABILITY_PROMPT)
        assert tokens <= _WIDGET_CAPABILITY_CAP, f"<widget_capability> is {tokens} tokens, over the {_WIDGET_CAPABILITY_CAP} cap"

    @pytest.mark.parametrize("surface", sorted(_MARKERS_BY_SURFACE))
    def test_assembly_measures_every_block(self, surface: str) -> None:
        """A gate that measured an empty or partial assembly would pass forever."""
        text = _static_first_message(surface, "en")
        for marker in _MARKERS_BY_SURFACE[surface]:
            assert marker in text, f"{surface}: {marker}"
