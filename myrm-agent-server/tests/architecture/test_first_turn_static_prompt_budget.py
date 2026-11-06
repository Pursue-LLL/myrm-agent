"""Architecture gate: token budget of the static part of the first system message.

``messages[0]`` of an Agent turn starts with the server core prompt, followed by harness blocks
(datetime rules, agent core rules, channel output hint). Those parts are pure functions of
(prompt mode, locale, channel), so their size is pinned here without any model call.

Every cap is the size measured after the last deliberate prompt change plus 5%. A change that adds text
must raise the cap in the same PR and say why, so the first turn cannot grow unnoticed.

Left out on purpose: the host environment line and the cache canary (they vary per host / process) and
the CLI tool section (mounted at runtime); none of them is decided by prompt text.
"""

from __future__ import annotations

import pytest
import tiktoken
from myrm_agent_harness.agent.streaming.agent_core_rules import AGENT_CORE_RULES
from myrm_agent_harness.agent.streaming.channel_output_hints import resolve_channel_output_hint
from myrm_agent_harness.agent.streaming.utils import DATETIME_SYSTEM_RULES

from app.ai_agents.agent_middlewares.widget_capability_middleware import WIDGET_CAPABILITY_PROMPT
from app.ai_agents.prompts.general_agent_prompt import get_core_system_prompt

# o200k_base is the harness planning encoding. Measured: zh-CN 1303, en 1107 (the same for every model).
# Cap = measured * 1.05 rounded up.
_ENCODING_NAME = "o200k_base"
_STATIC_FIRST_MESSAGE_CAPS: dict[str, int] = {
    "zh-CN": 1369,
    "en": 1163,
}
# Measured 348 tokens; the block rides in every web turn. Cap = measured * 1.05 rounded up.
_WIDGET_CAPABILITY_CAP = 366


def _token_count(text: str) -> int:
    return len(tiktoken.get_encoding(_ENCODING_NAME).encode(text, disallowed_special=()))


def _static_first_message(locale: str) -> str:
    """Assemble the static blocks in the order the agent appends them to the system prompt."""
    return (
        get_core_system_prompt("full", enable_answer_tool=False, locale=locale)
        + DATETIME_SYSTEM_RULES
        + AGENT_CORE_RULES
        + resolve_channel_output_hint("web_chat")
    )


@pytest.mark.architecture
class TestFirstTurnStaticPromptBudget:
    """CI gate: the static first system message and the widget capability block stay within their caps."""

    @pytest.mark.parametrize("locale", sorted(_STATIC_FIRST_MESSAGE_CAPS))
    def test_static_first_message_within_cap(self, locale: str) -> None:
        cap = _STATIC_FIRST_MESSAGE_CAPS[locale]
        tokens = _token_count(_static_first_message(locale))
        assert tokens <= cap, (
            f"static first system message for {locale} is {tokens} tokens, over the {cap} cap; "
            "trim the added text, or raise the cap in this PR and explain the cost and benefit"
        )

    def test_widget_capability_prompt_within_cap(self) -> None:
        tokens = _token_count(WIDGET_CAPABILITY_PROMPT)
        assert tokens <= _WIDGET_CAPABILITY_CAP, f"<widget_capability> is {tokens} tokens, over the {_WIDGET_CAPABILITY_CAP} cap"

    def test_assembly_measures_every_block(self) -> None:
        """A gate that measured an empty or partial assembly would pass forever."""
        text = _static_first_message("en")
        for marker in (
            "<identity>",
            "<response_rules>",
            "<task_integrity>",
            "<datetime_rules>",
            "<agent_behavior_rules>",
            "[Output Format]",
        ):
            assert marker in text, marker
