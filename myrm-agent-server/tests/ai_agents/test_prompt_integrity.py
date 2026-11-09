"""Tests for system prompt integrity across the Prompt Modes.

Validates that CORE_SYSTEM_PROMPT correctly assembles all rule blocks,
that each mode (full/search) contains the expected components,
and that prompt strings are stable for KV Cache optimization.
"""

import pytest
from myrm_agent_harness.core.security.detection.content_boundary import SECURITY_BOUNDARY_SYSTEM_RULES

from app.ai_agents.prompts.general_agent_prompt import (
    CORE_SYSTEM_PROMPT,
    coerce_prompt_mode,
    get_citation_rules_if_needed,
    get_core_system_prompt,
)
from app.ai_agents.prompts.shared_rules import (
    AGENT_RESPONSE_RULES_EN,
    DESKTOP_CONTROL_RULES,
    EXTERNAL_SOURCES_CITATION_RULES,
    SEARCH_RESPONSE_RULES_EN,
    TASK_INTEGRITY_RULES,
)


class TestCoreSystemPrompt:
    """Full mode prompt tests."""

    def test_contains_all_rule_blocks(self) -> None:
        prompt = get_core_system_prompt()
        assert "<identity>" in prompt
        assert "<response_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_task_integrity_content(self) -> None:
        assert "Never unilaterally simplify" in TASK_INTEGRITY_RULES
        assert "Never assume the task is complete" in TASK_INTEGRITY_RULES
        assert "explicitly ask the user first" in TASK_INTEGRITY_RULES
        assert "ENTIRE session" in TASK_INTEGRITY_RULES
        assert "NEVER execute destructive terminal commands" in TASK_INTEGRITY_RULES

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
        response_pos = prompt.index("<response_rules>")
        integrity_pos = prompt.index("<task_integrity>")

        assert identity_pos < response_pos < integrity_pos

    def test_shared_rules_exports(self) -> None:
        assert len(SECURITY_BOUNDARY_SYSTEM_RULES) > 0
        assert len(AGENT_RESPONSE_RULES_EN) > 0
        assert len(SEARCH_RESPONSE_RULES_EN) > 0
        assert len(TASK_INTEGRITY_RULES) > 0
        assert len(EXTERNAL_SOURCES_CITATION_RULES) > 0


class TestPromptModes:
    """Validates the two Prompt Modes (full/search)."""

    def test_full_mode_contains_all_blocks(self) -> None:
        prompt = get_core_system_prompt("full")
        assert "<identity>" in prompt
        assert "<response_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_search_mode_is_the_search_prompt(self) -> None:
        prompt = get_core_system_prompt("search")
        assert "<search_conditions" in prompt
        assert "<task_integrity>" not in prompt
        assert prompt is not CORE_SYSTEM_PROMPT

    def test_full_mode_is_the_default(self) -> None:
        """get_core_system_prompt() with no arg returns CORE_SYSTEM_PROMPT."""
        assert get_core_system_prompt() is CORE_SYSTEM_PROMPT
        assert get_core_system_prompt("full") is CORE_SYSTEM_PROMPT

    def test_invalid_mode_fallback_to_full(self) -> None:
        """Unknown mode should fallback to full for safety."""
        result = get_core_system_prompt("invalid_mode")  # type: ignore[arg-type]
        assert result is CORE_SYSTEM_PROMPT

    def test_prompt_stability_across_calls(self) -> None:
        """Same mode always returns the exact same object (KV Cache stability)."""
        for mode in ("full", "search"):
            first = get_core_system_prompt(mode)  # type: ignore[arg-type]
            second = get_core_system_prompt(mode)  # type: ignore[arg-type]
            assert first is second

    def test_prompt_stability_all_param_combos(self) -> None:
        """All enable_answer_tool combos return stable objects."""
        for answer in (True, False):
            for mode in ("full", "search"):
                a = get_core_system_prompt(mode, enable_answer_tool=answer)  # type: ignore[arg-type]
                b = get_core_system_prompt(mode, enable_answer_tool=answer)  # type: ignore[arg-type]
                assert a is b


class TestSystemPromptDecoupledFromMemoryTools:
    """Validates System Prompt is completely decoupled from memory tools.

    Memory SOP rules live strictly inside memory tool descriptions (Self-contained),
    keeping the core system prompt pure and free of memory tool references.
    """

    @pytest.mark.parametrize("mode", ["full", "search"])
    def test_all_modes_never_have_memory_rules(self, mode: str) -> None:
        """System prompt must never leak memory_rules or memory tool names in any mode."""
        prompt = get_core_system_prompt(mode)  # type: ignore[arg-type]
        assert "<memory_rules>" not in prompt
        assert "memory_save_tool" not in prompt
        assert "memory_manage_tool" not in prompt
        assert "memory_search_tool" not in prompt

    def test_prompt_still_has_all_core_rule_blocks(self) -> None:
        """Core rules must remain present and intact."""
        prompt = get_core_system_prompt("full")
        assert "<identity>" in prompt
        assert "<response_rules>" in prompt
        assert "<task_integrity>" in prompt

    def test_answer_tool_disabled_full_mode_still_has_core_rules(self) -> None:
        """enable_answer_tool=False still has core rules."""
        prompt = get_core_system_prompt("full", enable_answer_tool=False)
        assert "<identity>" in prompt
        assert "<task_integrity>" in prompt
        assert "request_answer_user_tool" not in prompt

    def test_answer_tool_disabled_no_answer_tool_references(self) -> None:
        """No answer tool references when answer tool disabled."""
        prompt = get_core_system_prompt("full", enable_answer_tool=False)
        assert "answer_tool_required" not in prompt

    def test_invalid_mode_falls_back_to_full(self) -> None:
        """Unknown mode falls back to full."""
        result = get_core_system_prompt("unknown_mode")  # type: ignore[arg-type]
        expected = get_core_system_prompt("full")
        assert result is expected


class TestPromptTokenBudgetGate:
    """Prevents prompt bloat regression via an absolute token cap.

    If any assertion fails, the prompt has grown beyond the budget — review
    the change and either trim back or deliberately raise the cap with a PR
    comment explaining the token cost / benefit.
    """

    _ENCODING_NAME = "cl100k_base"
    _FULL_TOKEN_CAP = 2000

    @staticmethod
    def _token_count(text: str) -> int:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    def test_full_mode_prompt_token_cap(self) -> None:
        """Full prompt must stay within budget to control Turn1 cost."""
        full = get_core_system_prompt("full")
        tokens = self._token_count(full)
        assert tokens <= self._FULL_TOKEN_CAP, f"full prompt {tokens} tokens exceeds cap {self._FULL_TOKEN_CAP}"


class TestDesktopControlRules:
    """Validates DESKTOP_CONTROL_RULES stays aligned with desktop tool capabilities."""

    def test_rules_disclose_target_scope(self) -> None:
        assert 'scope="target"' in DESKTOP_CONTROL_RULES
        assert 'app_name="<app name>"' in DESKTOP_CONTROL_RULES
        assert "desktop_snapshot_tool" in DESKTOP_CONTROL_RULES

    def test_rules_disclose_query_and_wait(self) -> None:
        assert 'query="<search term>"' in DESKTOP_CONTROL_RULES
        assert "wait_seconds=" in DESKTOP_CONTROL_RULES

    def test_rules_do_not_mention_window_title(self) -> None:
        """app_name must stay an app-name hint; 'window name' is unsupported on macOS."""
        assert "window name" not in DESKTOP_CONTROL_RULES

    def test_rules_forbid_operator_as_key_name(self) -> None:
        """Printable operators must not be used as press/key names (calculator pitfall)."""
        assert "printable operators" in DESKTOP_CONTROL_RULES
        for operator in ("*", "/", "+", "-", "%", "="):
            assert f'"{operator}"' in DESKTOP_CONTROL_RULES
        assert "desktop_vision_tool key=" in DESKTOP_CONTROL_RULES
        assert "calculator/@dref" in DESKTOP_CONTROL_RULES
        assert "action=press activates" in DESKTOP_CONTROL_RULES


class TestPromptBilingualSupport:
    """Validates full bilingual (EN/ZH) system prompt support with English default."""

    def test_default_locale_is_english(self) -> None:
        prompt = get_core_system_prompt()
        assert "You are a powerful, pragmatic, and versatile AI assistant" in prompt
        assert "Never unilaterally simplify" in prompt
        assert "<task_integrity>" in prompt

    def test_explicit_chinese_locale_switches_to_chinese(self) -> None:
        prompt = get_core_system_prompt(locale="zh-CN")
        assert "你是一个功能强大且求真务实的通用AI智能助手" in prompt
        assert "用户的原始目标和所有约束" in prompt
        assert "<task_integrity>" in prompt

    def test_citation_rules_bilingual(self) -> None:
        from app.ai_agents.prompts.shared_rules import (
            EXTERNAL_SOURCES_CITATION_RULES_EN,
            EXTERNAL_SOURCES_CITATION_RULES_ZH,
        )

        assert get_citation_rules_if_needed(True, locale="en") == EXTERNAL_SOURCES_CITATION_RULES_EN
        assert get_citation_rules_if_needed(True, locale="zh-CN") == EXTERNAL_SOURCES_CITATION_RULES_ZH
        assert get_citation_rules_if_needed(False, locale="en") is None

    def test_stability_across_locales(self) -> None:
        assert get_core_system_prompt(locale="en") is get_core_system_prompt(locale="en")
        assert get_core_system_prompt(locale="zh-CN") is get_core_system_prompt(locale="zh")
        assert get_core_system_prompt(locale="en") is not get_core_system_prompt(locale="zh-CN")


class TestCoercePromptMode:
    """Stored prompt modes are free-form strings; only known modes select a non-full prompt."""

    @pytest.mark.parametrize("mode", ["full", "search"])
    def test_known_modes_are_kept(self, mode: str) -> None:
        assert coerce_prompt_mode(mode) == mode

    @pytest.mark.parametrize("mode", ["", "FULL", "legacy", "search ", "lean", "naked"])
    def test_unknown_modes_fall_back_to_full(self, mode: str) -> None:
        assert coerce_prompt_mode(mode) == "full"
        assert get_core_system_prompt(coerce_prompt_mode(mode)) is get_core_system_prompt("full")


class TestUserInstructionPrecedence:
    """The precedence of the user's instructions is declared once, by the header of their own message."""

    @pytest.mark.parametrize("mode", ["full", "search"])
    @pytest.mark.parametrize("locale", ["en", "zh-CN"])
    def test_static_prompt_does_not_restate_the_precedence(self, mode: str, locale: str) -> None:
        prompt = get_core_system_prompt(mode, locale=locale)  # type: ignore[arg-type]
        assert "<user_instructions" not in prompt
