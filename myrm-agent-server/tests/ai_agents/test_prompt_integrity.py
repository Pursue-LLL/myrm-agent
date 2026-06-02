"""Tests for system prompt integrity across all Prompt Mode tiers.

Validates that CORE_SYSTEM_PROMPT correctly assembles all rule blocks,
that each mode (full/lean/naked) contains the expected components,
and that prompt strings are stable for KV Cache optimization.
"""

import pytest

from app.ai_agents.prompts.general_agent_prompt import (
    CORE_SYSTEM_PROMPT,
    get_citation_rules_if_needed,
    get_core_system_prompt,
)
from app.ai_agents.prompts.shared_rules import (
    ABSOLUTE_OBEDIENCE_RULES,
    EXTERNAL_SOURCES_CITATION_RULES,
    RESPONSE_RULES,
    SECURITY_RULES,
    TASK_INTEGRITY_RULES,
)


class TestCoreSystemPrompt:
    """Full mode prompt tests."""

    def test_contains_all_rule_blocks(self) -> None:
        prompt = get_core_system_prompt()
        assert "<identity>" in prompt
        assert "<absolute_obedience_override>" in prompt
        assert "<response_rules>" in prompt
        assert "<security_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_task_integrity_content(self) -> None:
        assert "Never unilaterally simplify" in TASK_INTEGRITY_RULES
        assert "Never assume the task is complete" in TASK_INTEGRITY_RULES
        assert "explicitly ask the user first" in TASK_INTEGRITY_RULES
        assert "ENTIRE session" in TASK_INTEGRITY_RULES

    def test_task_integrity_in_core_prompt(self) -> None:
        assert TASK_INTEGRITY_RULES.strip() in CORE_SYSTEM_PROMPT

    def test_get_core_system_prompt_returns_constant(self) -> None:
        assert get_core_system_prompt() is CORE_SYSTEM_PROMPT

    def test_citation_rules_conditional(self) -> None:
        assert get_citation_rules_if_needed(True) == EXTERNAL_SOURCES_CITATION_RULES
        assert get_citation_rules_if_needed(False) is None

    def test_rule_ordering(self) -> None:
        """Rules should appear in correct order for prompt cache stability."""
        prompt = CORE_SYSTEM_PROMPT
        identity_pos = prompt.index("<identity>")
        obedience_pos = prompt.index("<absolute_obedience_override>")
        response_pos = prompt.index("<response_rules>")
        security_pos = prompt.index("<security_rules>")
        integrity_pos = prompt.index("<task_integrity>")

        assert identity_pos < obedience_pos < response_pos < security_pos < integrity_pos

    def test_shared_rules_exports(self) -> None:
        assert len(ABSOLUTE_OBEDIENCE_RULES) > 0
        assert len(SECURITY_RULES) > 0
        assert len(RESPONSE_RULES) > 0
        assert len(TASK_INTEGRITY_RULES) > 0
        assert len(EXTERNAL_SOURCES_CITATION_RULES) > 0


class TestPromptModeThreeTier:
    """Validates three-tier Prompt Mode (full/lean/naked) correctness."""

    def test_full_mode_contains_all_blocks(self) -> None:
        prompt = get_core_system_prompt("full")
        assert "<identity>" in prompt
        assert "<absolute_obedience_override>" in prompt
        assert "<response_rules>" in prompt
        assert "<security_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_lean_mode_has_identity_security_integrity(self) -> None:
        prompt = get_core_system_prompt("lean")
        assert "<identity>" in prompt
        assert "<security_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_lean_mode_excludes_formatting_rules(self) -> None:
        prompt = get_core_system_prompt("lean")
        assert "<response_rules>" not in prompt
        assert "<absolute_obedience_override>" not in prompt

    def test_naked_mode_has_security_and_tool_guidance(self) -> None:
        prompt = get_core_system_prompt("naked")
        assert "<security_rules>" in prompt
        assert "<tool_guidance>" in prompt

    def test_naked_mode_excludes_identity_and_formatting(self) -> None:
        prompt = get_core_system_prompt("naked")
        assert "<identity>" not in prompt
        assert "<response_rules>" not in prompt
        assert "<absolute_obedience_override>" not in prompt
        assert "<task_integrity>" not in prompt

    def test_mode_size_ordering(self) -> None:
        """full > lean > naked in character count."""
        full = get_core_system_prompt("full")
        lean = get_core_system_prompt("lean")
        naked = get_core_system_prompt("naked")
        assert len(full) > len(lean) > len(naked)

    def test_naked_mode_is_minimal(self) -> None:
        """Naked mode should be under 1000 chars to maximize user control."""
        naked = get_core_system_prompt("naked")
        assert len(naked) < 1000

    def test_full_mode_backward_compat(self) -> None:
        """get_core_system_prompt() with no arg returns CORE_SYSTEM_PROMPT."""
        assert get_core_system_prompt() is CORE_SYSTEM_PROMPT
        assert get_core_system_prompt("full") is CORE_SYSTEM_PROMPT

    def test_invalid_mode_fallback_to_full(self) -> None:
        """Unknown mode should fallback to full for safety."""
        result = get_core_system_prompt("invalid_mode")  # type: ignore[arg-type]
        assert result is CORE_SYSTEM_PROMPT

    def test_prompt_stability_across_calls(self) -> None:
        """Same mode always returns the exact same object (KV Cache stability)."""
        for mode in ("full", "lean", "naked"):
            first = get_core_system_prompt(mode)  # type: ignore[arg-type]
            second = get_core_system_prompt(mode)  # type: ignore[arg-type]
            assert first is second

    @pytest.mark.parametrize("mode", ["full", "lean", "naked"])
    def test_all_modes_have_security_rules(self, mode: str) -> None:
        """Security rules must always be present regardless of mode."""
        prompt = get_core_system_prompt(mode)  # type: ignore[arg-type]
        assert "<security_rules>" in prompt

    def test_prompt_stability_all_param_combos(self) -> None:
        """All (enable_answer_tool, enable_memory) combos return stable objects."""
        for answer in (True, False):
            for memory in (True, False):
                for mode in ("full", "lean", "naked"):
                    a = get_core_system_prompt(mode, enable_answer_tool=answer, enable_memory=memory)  # type: ignore[arg-type]
                    b = get_core_system_prompt(mode, enable_answer_tool=answer, enable_memory=memory)  # type: ignore[arg-type]
                    assert a is b


class TestMemoryRulesConditionalInjection:
    """Validates MEMORY_RULES are only injected when enable_memory=True."""

    def test_full_mode_includes_memory_rules_by_default(self) -> None:
        prompt = get_core_system_prompt("full")
        assert "<memory_rules>" in prompt
        assert "memory_save" in prompt

    def test_full_mode_excludes_memory_rules_when_disabled(self) -> None:
        prompt = get_core_system_prompt("full", enable_memory=False)
        assert "<memory_rules>" not in prompt
        assert "memory_save" not in prompt

    def test_lean_mode_never_has_memory_rules(self) -> None:
        for memory in (True, False):
            prompt = get_core_system_prompt("lean", enable_memory=memory)
            assert "<memory_rules>" not in prompt

    def test_naked_mode_never_has_memory_rules(self) -> None:
        for memory in (True, False):
            prompt = get_core_system_prompt("naked", enable_memory=memory)
            assert "<memory_rules>" not in prompt

    def test_memory_disabled_still_has_other_rules(self) -> None:
        """Disabling memory must not affect other rule blocks."""
        prompt = get_core_system_prompt("full", enable_memory=False)
        assert "<identity>" in prompt
        assert "<absolute_obedience_override>" in prompt
        assert "<response_rules>" in prompt
        assert "<security_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_memory_disabled_prompt_is_shorter(self) -> None:
        with_mem = get_core_system_prompt("full", enable_memory=True)
        without_mem = get_core_system_prompt("full", enable_memory=False)
        assert len(with_mem) > len(without_mem)

    def test_memory_disabled_no_memory_tool_references(self) -> None:
        """No memory tool names should leak when memory is disabled."""
        prompt = get_core_system_prompt("full", enable_memory=False)
        assert "memory_save" not in prompt
        assert "memory_manage" not in prompt
        assert "memory_recall" not in prompt

    def test_both_disabled_full_mode_still_has_core_rules(self) -> None:
        """enable_answer_tool=False + enable_memory=False still has core rules."""
        prompt = get_core_system_prompt(
            "full", enable_answer_tool=False, enable_memory=False
        )
        assert "<identity>" in prompt
        assert "<security_rules>" in prompt
        assert "<task_integrity>" in prompt
        assert "request_answer_user_tool" not in prompt
        assert "<memory_rules>" not in prompt

    def test_both_disabled_no_answer_tool_references(self) -> None:
        """No answer tool references when both features disabled."""
        prompt = get_core_system_prompt(
            "full", enable_answer_tool=False, enable_memory=False
        )
        assert "answer_tool_required" not in prompt

    def test_invalid_mode_with_memory_disabled_falls_back(self) -> None:
        """Unknown mode + enable_memory=False falls back to full without memory."""
        result = get_core_system_prompt(
            "unknown_mode", enable_memory=False  # type: ignore[arg-type]
        )
        expected = get_core_system_prompt("full", enable_memory=False)
        assert result is expected
