"""Architecture gate: token budget of the static part of the first system message.

``messages[0]`` of an Agent turn starts with the server core prompt, followed by harness blocks
(datetime rules, per-model execution discipline, channel output hint). Those parts are pure functions of
(prompt mode, locale, model name, channel), so their size is pinned here without any model call.

Every cap is the size measured after the last deliberate prompt change plus 5%. A change that adds text
must raise the cap in the same PR and say why, so the first turn cannot grow unnoticed.

Left out on purpose: the host environment line and the cache canary (they vary per host / process) and
the CLI tool section (mounted at runtime); none of them is decided by prompt text.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import tiktoken
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.agent.streaming.channel_output_hints import resolve_channel_output_hint
from myrm_agent_harness.agent.streaming.model_discipline import resolve_execution_discipline
from myrm_agent_harness.agent.streaming.utils import DATETIME_SYSTEM_RULES

from app.ai_agents.agent_middlewares.widget_capability_middleware import WIDGET_CAPABILITY_PROMPT
from app.ai_agents.prompts.general_agent_prompt import get_core_system_prompt

# o200k_base is the harness planning encoding. Measured 2026-11-03 (zh-CN / en), cap = measured * 1.05 rounded up:
#   gpt-5 1969 / 1773, claude-sonnet 1585 / 1389, claude-opus 1762 / 1566, gemini 1629 / 1433, deepseek 1572 / 1376.
_ENCODING_NAME = "o200k_base"
_STATIC_FIRST_MESSAGE_CAPS: dict[tuple[str, str], int] = {
    ("gpt-5", "zh-CN"): 2068,
    ("gpt-5", "en"): 1862,
    ("claude-sonnet-4-5", "zh-CN"): 1665,
    ("claude-sonnet-4-5", "en"): 1459,
    ("claude-opus-5", "zh-CN"): 1851,
    ("claude-opus-5", "en"): 1645,
    ("gemini-2.5-pro", "zh-CN"): 1711,
    ("gemini-2.5-pro", "en"): 1505,
    ("deepseek-chat", "zh-CN"): 1651,
    ("deepseek-chat", "en"): 1445,
}
# Measured 348 on 2026-11-03; the block rides in every web turn and had no cap before.
_WIDGET_CAPABILITY_CAP = 366


def _token_count(text: str) -> int:
    return len(tiktoken.get_encoding(_ENCODING_NAME).encode(text, disallowed_special=()))


def _static_first_message(model_name: str, locale: str) -> str:
    """Assemble the static blocks in the order the agent appends them to the system prompt."""
    llm = MagicMock(spec=BaseChatModel)
    llm.model_name = model_name
    return (
        get_core_system_prompt("full", enable_answer_tool=False, locale=locale)
        + DATETIME_SYSTEM_RULES
        + resolve_execution_discipline(llm)
        + resolve_channel_output_hint("web_chat")
    )


@pytest.mark.architecture
class TestFirstTurnStaticPromptBudget:
    """CI gate: the static first system message and the widget capability block stay within their caps."""

    @pytest.mark.parametrize(("model_name", "locale"), sorted(_STATIC_FIRST_MESSAGE_CAPS))
    def test_static_first_message_within_cap(self, model_name: str, locale: str) -> None:
        cap = _STATIC_FIRST_MESSAGE_CAPS[(model_name, locale)]
        tokens = _token_count(_static_first_message(model_name, locale))
        assert tokens <= cap, (
            f"static first system message for {model_name}/{locale} is {tokens} tokens, over the {cap} cap; "
            "trim the added text, or raise the cap in this PR and explain the cost and benefit"
        )

    def test_widget_capability_prompt_within_cap(self) -> None:
        tokens = _token_count(WIDGET_CAPABILITY_PROMPT)
        assert tokens <= _WIDGET_CAPABILITY_CAP, f"<widget_capability> is {tokens} tokens, over the {_WIDGET_CAPABILITY_CAP} cap"

    def test_assembly_measures_every_block(self) -> None:
        """A gate that measured an empty or partial assembly would pass forever."""
        text = _static_first_message("gpt-5", "en")
        for marker in (
            "<identity>",
            "<response_rules>",
            "<task_integrity>",
            "<datetime_rules>",
            "<execution_discipline>",
            "[Output Format]",
        ):
            assert marker in text, marker
