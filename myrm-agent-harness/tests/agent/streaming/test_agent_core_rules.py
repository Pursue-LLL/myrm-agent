"""agent_core_rules.py unit tests

Covers the public/internal functions and constants:
- AGENT_CORE_RULES: the one rule block every model gets
- _extract_model_name: model name extraction from LLM instances
- resolve_escalation_contract: conditional self-upgrade contract
- BaseAgent system prompt assembly: identical for every model name
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.streaming.agent_core_rules import (
    _ESCALATION_CONTRACT_TEMPLATE,
    AGENT_CORE_RULES,
    _extract_model_name,
    resolve_escalation_contract,
)
from myrm_agent_harness.agent.types import AgentRuntimeConfig


def _make_llm(model_name: str | None = None, model: str | None = None) -> BaseChatModel:
    """Create a mock LLM with configurable model_name / model attributes."""
    llm = MagicMock(spec=BaseChatModel)
    if model_name is not None:
        llm.model_name = model_name
    else:
        del llm.model_name
    if model is not None:
        llm.model = model
    else:
        del llm.model
    return llm


# ============================================================================
# AGENT_CORE_RULES constant
# ============================================================================


class TestAgentCoreRules:
    def test_wrapped_in_xml_tags(self) -> None:
        assert AGENT_CORE_RULES.startswith("\n<agent_behavior_rules>")
        assert AGENT_CORE_RULES.endswith("</agent_behavior_rules>")

    def test_anti_narration_present(self) -> None:
        assert "NEVER narrate" in AGENT_CORE_RULES
        assert "FINAL ANSWER" in AGENT_CORE_RULES

    def test_narration_examples_are_bilingual(self) -> None:
        assert "让我查一下" in AGENT_CORE_RULES
        assert "搜索中" in AGENT_CORE_RULES
        assert "I will use" in AGENT_CORE_RULES

    def test_tool_honesty_present(self) -> None:
        assert "NEVER fabricate" in AGENT_CORE_RULES
        assert "No results found" in AGENT_CORE_RULES
        assert "report the error" in AGENT_CORE_RULES

    def test_anti_negative_claim_present(self) -> None:
        assert "Negative claims" in AGENT_CORE_RULES

    def test_anti_negative_claim_requires_verification(self) -> None:
        assert "verification tool" in AGENT_CORE_RULES

    def test_anti_negative_claim_evidence_required(self) -> None:
        assert "tool name and" in AGENT_CORE_RULES
        assert "query as evidence" in AGENT_CORE_RULES

    def test_anti_negative_claim_no_tool_fallback(self) -> None:
        assert "I have not verified this" in AGENT_CORE_RULES

    def test_xml_tool_call_defense_present(self) -> None:
        assert "<tool_call>" in AGENT_CORE_RULES
        assert "NEVER output <tool_call>" in AGENT_CORE_RULES
        assert "Function Calling API" in AGENT_CORE_RULES

    def test_context_first_check_present(self) -> None:
        assert "conversation context" in AGENT_CORE_RULES
        assert "redundant tool calls" in AGENT_CORE_RULES.lower()

    def test_proactive_grounding_search_present(self) -> None:
        assert "ALWAYS search before asserting facts" in AGENT_CORE_RULES
        assert "knowledge cutoff" in AGENT_CORE_RULES

    def test_grounding_search_is_conditional_on_a_search_tool(self) -> None:
        """An agent can run without web search, so the rule must not demand a search it cannot make."""
        assert "When a search tool is available, ALWAYS search" in AGENT_CORE_RULES

    def test_does_not_claim_tool_calls_are_invisible(self) -> None:
        """The web UI and the IM channels both show every tool call to the user."""
        assert "invisible" not in AGENT_CORE_RULES

    def test_proactive_capability_discovery_present(self) -> None:
        assert "declining a user request" in AGENT_CORE_RULES
        assert "discovery or search tool" in AGENT_CORE_RULES

    def test_search_query_guidance_not_in_agent_core_rules(self) -> None:
        assert "Query Rewriting Rules" not in AGENT_CORE_RULES

    def test_does_not_tell_the_model_to_hand_the_clock_to_a_tool(self) -> None:
        """The user's clock comes from <current_datetime>; a shell on the host may sit in another timezone."""
        assert "Current time" not in AGENT_CORE_RULES
        assert "What time is it" not in AGENT_CORE_RULES
        assert "use a shell tool" not in AGENT_CORE_RULES

    def test_proactive_search_before_xml_close(self) -> None:
        """Proactive capability discovery rule is inside the XML block."""
        close_tag_pos = AGENT_CORE_RULES.index("</agent_behavior_rules>")
        rule_pos = AGENT_CORE_RULES.index("declining a user request")
        assert rule_pos < close_tag_pos


# ============================================================================
# _extract_model_name
# ============================================================================


class TestExtractModelName:
    def test_uses_model_name_attr(self) -> None:
        assert _extract_model_name(_make_llm(model_name="GPT-4o")) == "gpt-4o"

    def test_falls_back_to_model_attr(self) -> None:
        assert _extract_model_name(_make_llm(model="Claude-3.5-Sonnet")) == "claude-3.5-sonnet"

    def test_model_name_takes_precedence(self) -> None:
        assert _extract_model_name(_make_llm(model_name="GPT-4o", model="claude-3")) == "gpt-4o"

    def test_empty_model_name_falls_back(self) -> None:
        assert _extract_model_name(_make_llm(model_name="", model="Gemini-2.0")) == "gemini-2.0"

    def test_no_attrs_returns_empty(self) -> None:
        assert _extract_model_name(_make_llm()) == ""

    def test_always_returns_lowercase(self) -> None:
        assert _extract_model_name(_make_llm(model_name="DEEPSEEK-R1")) == "deepseek-r1"

    def test_non_string_attrs_are_ignored(self) -> None:
        """A wrapper or test double may expose non-string attributes; the resolver must not crash on them."""
        assert _extract_model_name(MagicMock(spec=BaseChatModel)) == ""

    def test_non_string_model_name_falls_back_to_a_string_model_attr(self) -> None:
        llm = MagicMock(spec=BaseChatModel)
        llm.model = "GPT-4o"
        assert _extract_model_name(llm) == "gpt-4o"


# ============================================================================
# resolve_escalation_contract
# ============================================================================


class TestResolveEscalationContract:
    def test_no_target_returns_empty(self) -> None:
        assert resolve_escalation_contract(_make_llm(model_name="gpt-4o"), None) == ""

    def test_same_model_returns_empty(self) -> None:
        llm = _make_llm(model_name="gpt-4o")
        assert resolve_escalation_contract(llm, _make_llm(model_name="gpt-4o")) == ""

    def test_different_models_returns_contract(self) -> None:
        result = resolve_escalation_contract(_make_llm(model_name="deepseek-v3-flash"), _make_llm(model_name="gpt-4o"))
        assert "<<<NEEDS_PRO>>>" in result
        assert "deepseek-v3-flash" in result
        assert "gpt-4o" in result

    def test_contract_contains_xml_tags(self) -> None:
        result = resolve_escalation_contract(
            _make_llm(model_name="gpt-4o-mini"), _make_llm(model_name="claude-3.5-sonnet")
        )
        assert "<escalation_contract>" in result
        assert "</escalation_contract>" in result

    def test_contract_mentions_sparingly(self) -> None:
        result = resolve_escalation_contract(_make_llm(model_name="deepseek-chat"), _make_llm(model_name="deepseek-r1"))
        assert "sparingly" in result

    def test_empty_model_name_returns_empty(self) -> None:
        assert resolve_escalation_contract(_make_llm(model_name=""), _make_llm(model_name="gpt-4o")) == ""

    def test_empty_target_name_returns_empty(self) -> None:
        assert resolve_escalation_contract(_make_llm(model_name="gpt-4o"), _make_llm(model_name="")) == ""

    def test_idempotent(self) -> None:
        """KV cache safety: same inputs produce identical output."""
        llm = _make_llm(model_name="deepseek-v3-flash")
        target = _make_llm(model_name="gpt-4o")
        assert resolve_escalation_contract(llm, target) == resolve_escalation_contract(llm, target)

    def test_template_uses_format_correctly(self) -> None:
        assert "{current_model}" in _ESCALATION_CONTRACT_TEMPLATE
        assert "{target_model}" in _ESCALATION_CONTRACT_TEMPLATE


# ============================================================================
# BaseAgent system prompt assembly
# ============================================================================


class _NamedChatModel(FakeListChatModel):
    """Scripted chat model that reports a model name the way a provider adapter does."""

    model_name: str = ""


_MODEL_NAMES = (
    "gpt-5",
    "gpt-5-codex",
    "claude-opus-5",
    "claude-sonnet-4.5",
    "gemini-2.5-pro",
    "grok-4",
    "qwen3-max",
    "deepseek-v3.2",
)


async def _assemble_system_prompt(model_name: str) -> str:
    """Run the real BaseAgent initialization and return the first system message it caches."""
    agent = BaseAgent(
        llm=_NamedChatModel(responses=["ok"], model_name=model_name),
        system_prompt="BASE",
        config=AgentRuntimeConfig(channel_name="web_chat"),
    )
    with (
        patch("myrm_agent_harness.agent.base_agent.create_agent", return_value=MagicMock()),
        # The canary is random per agent; fixing it leaves model-dependent text as the only source of a difference.
        patch("myrm_agent_harness.agent.security.detection.canary_guard.generate_canary", return_value="canary"),
    ):
        await agent._ensure_initialized()
    assert agent._cached_system_prompt is not None
    return agent._cached_system_prompt


class TestSystemPromptIsModelAgnostic:
    """Without an escalation target, the assembly never looks at the model name."""

    async def test_prompt_is_identical_for_every_model_name(self) -> None:
        prompts = {name: await _assemble_system_prompt(name) for name in _MODEL_NAMES}
        reference = prompts[_MODEL_NAMES[0]]
        differing = [name for name, prompt in prompts.items() if prompt != reference]
        assert not differing, f"system prompt depends on the model name: {differing}"
        assert AGENT_CORE_RULES in reference
