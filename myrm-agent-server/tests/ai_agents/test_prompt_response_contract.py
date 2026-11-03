"""Tests for the prompt text contracts of the identity and the response rules.

The identity states the quality bar once; the Agent and Search response rules answer different jobs,
share only the LaTeX contract, and the Agent rules defer formatting to the channel's [Output Format].
"""

import pytest

from app.ai_agents.prompts import shared_rules
from app.ai_agents.prompts.general_agent_prompt import get_core_system_prompt
from app.ai_agents.prompts.shared_rules import (
    AGENT_RESPONSE_RULES_EN,
    AGENT_RESPONSE_RULES_ZH,
    SEARCH_RESPONSE_RULES_EN,
    SEARCH_RESPONSE_RULES_ZH,
)


class TestIdentityStatesQualityBar:
    """The identity keeps the pinned persona opening and states the quality bar once, without slogans."""

    @pytest.mark.parametrize("mode", ["full", "lean"])
    def test_zh_identity(self, mode: str) -> None:
        identity = get_core_system_prompt(mode, locale="zh-CN").split("</identity>")[0]
        assert "你是一个功能强大且求真务实的通用AI智能助手" in identity
        assert "你的答案应当**事实准确**、时效性强，并对用户真正有用。" in identity
        assert "让用户惊叹" not in identity
        assert "绝不提供平庸" not in identity

    @pytest.mark.parametrize("mode", ["full", "lean"])
    def test_en_identity(self, mode: str) -> None:
        identity = get_core_system_prompt(mode, locale="en").split("</identity>")[0]
        assert "You are a powerful, pragmatic, and versatile AI assistant" in identity
        assert "Your answers should be **factually accurate**, timely, and genuinely useful to the user." in identity
        assert "ultra-high-quality" not in identity
        assert "comprehensive" not in identity


class TestResponseRulesSplit:
    """Agent and Search answer different jobs, so their response rules must not share quality text."""

    def test_agent_rules_scale_length_with_complexity(self) -> None:
        assert "comprehensive" not in AGENT_RESPONSE_RULES_EN.lower()
        assert "全面详细" not in AGENT_RESPONSE_RULES_ZH
        assert "Match length to the complexity of the question" in AGENT_RESPONSE_RULES_EN
        assert "篇幅与问题复杂度匹配" in AGENT_RESPONSE_RULES_ZH

    def test_agent_rules_keep_depth_for_complex_questions(self) -> None:
        assert "For complex ones, be thorough" in AGENT_RESPONSE_RULES_EN
        assert "复杂问题要充分展开" in AGENT_RESPONSE_RULES_ZH

    def test_agent_rules_drop_the_search_only_persona_line(self) -> None:
        assert "情绪值" not in AGENT_RESPONSE_RULES_ZH
        assert "Tone warmth" not in AGENT_RESPONSE_RULES_EN

    def test_search_rules_keep_comprehensive_synthesis(self) -> None:
        assert "comprehensive" in SEARCH_RESPONSE_RULES_EN.lower()
        assert "全面详细" in SEARCH_RESPONSE_RULES_ZH
        assert "情绪值" in SEARCH_RESPONSE_RULES_ZH

    def test_agent_formatting_defers_to_channel_output_format(self) -> None:
        assert "Follow the channel's [Output Format] declaration if present" in AGENT_RESPONSE_RULES_EN
        assert "unless the channel's [Output Format] says tables are unsupported or not allowed" in AGENT_RESPONSE_RULES_EN
        assert "有 [Output Format] 渠道提示时以其声明为准" in AGENT_RESPONSE_RULES_ZH
        assert "渠道 [Output Format] 不支持或不允许表格时除外" in AGENT_RESPONSE_RULES_ZH

    def test_latex_contract_is_shared_verbatim(self) -> None:
        for agent_rules, search_rules, marker in (
            (AGENT_RESPONSE_RULES_EN, SEARCH_RESPONSE_RULES_EN, "**Strict LaTeX math**"),
            (AGENT_RESPONSE_RULES_ZH, SEARCH_RESPONSE_RULES_ZH, "**严格的公式格式**"),
        ):
            assert agent_rules[agent_rules.index(marker) :] == search_rules[search_rules.index(marker) :]

    @pytest.mark.parametrize(
        ("locale", "agent_rules", "search_rules"),
        [
            ("en", AGENT_RESPONSE_RULES_EN, SEARCH_RESPONSE_RULES_EN),
            ("zh-CN", AGENT_RESPONSE_RULES_ZH, SEARCH_RESPONSE_RULES_ZH),
        ],
    )
    def test_modes_assemble_their_own_rules(self, locale: str, agent_rules: str, search_rules: str) -> None:
        assert agent_rules in get_core_system_prompt("full", locale=locale)
        assert search_rules not in get_core_system_prompt("full", locale=locale)
        assert search_rules in get_core_system_prompt("search", locale=locale)


class TestSharedRulesAreRenderedText:
    """Shared rule constants reach the model verbatim, so format escapes must not leak into them."""

    def test_no_format_escapes_in_shared_rule_constants(self) -> None:
        for name, value in vars(shared_rules).items():
            if name.isupper() and isinstance(value, str):
                assert "{{" not in value and "}}" not in value, name
