"""agent_core_rules.py unit tests

Covers:
- AGENT_CORE_RULES: the one rule block every model gets
- BaseAgent system prompt assembly: identical for every model name
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.streaming.agent_core_rules import AGENT_CORE_RULES
from myrm_agent_harness.agent.types import AgentRuntimeConfig

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

    def test_search_query_guidance_not_in_agent_core_rules(self) -> None:
        assert "Query Rewriting Rules" not in AGENT_CORE_RULES

    def test_does_not_tell_the_model_to_hand_the_clock_to_a_tool(self) -> None:
        """The user's clock comes from <current_datetime>; a shell on the host may sit in another timezone."""
        assert "Current time" not in AGENT_CORE_RULES
        assert "What time is it" not in AGENT_CORE_RULES
        assert "use a shell tool" not in AGENT_CORE_RULES

    def test_the_last_rule_is_inside_the_xml_block(self) -> None:
        close_tag_pos = AGENT_CORE_RULES.index("</agent_behavior_rules>")
        rule_pos = AGENT_CORE_RULES.index("redundant tool calls")
        assert rule_pos < close_tag_pos


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
    with patch("myrm_agent_harness.agent.base_agent.create_agent", return_value=MagicMock()):
        await agent._ensure_initialized()
    assert agent._cached_system_prompt is not None
    return agent._cached_system_prompt


class TestSystemPromptIsModelAgnostic:
    """The assembly never looks at the model name."""

    async def test_prompt_is_identical_for_every_model_name(self) -> None:
        prompts = {name: await _assemble_system_prompt(name) for name in _MODEL_NAMES}
        reference = prompts[_MODEL_NAMES[0]]
        differing = [name for name, prompt in prompts.items() if prompt != reference]
        assert not differing, f"system prompt depends on the model name: {differing}"
        assert AGENT_CORE_RULES in reference

    async def test_prompt_is_the_same_bytes_for_every_agent_and_carries_no_session_token(self) -> None:
        """A per-session token in the prompt would end the prefix the provider caches across sessions at that token."""
        first, second = await _assemble_system_prompt(_MODEL_NAMES[0]), await _assemble_system_prompt(_MODEL_NAMES[0])
        assert first == second
        assert "CANARY" not in first
