"""personality_templates 模块单元测试

验证模板定义的一致性、查询 API 的正确性、与 dto.py 类型定义的同步性。
"""

from __future__ import annotations

import pytest

from app.ai_agents.personality_templates import (
    DEFAULT_PERSONALITY_STYLE,
    PERSONALITY_TEMPLATES,
    PersonalityStyle,
    PersonalityTemplate,
    get_personality_template,
    is_valid_personality_style,
    list_all_personalities,
)
from app.database.dto import PersonalityStyleLiteral


class TestPersonalityTemplatesConsistency:
    """模板定义与 Literal 类型一致性测试"""

    def test_template_keys_match_literal_values(self) -> None:
        """PERSONALITY_TEMPLATES 的 key 必须与 PersonalityStyleLiteral 完全一致"""
        literal_values = set(PersonalityStyleLiteral.__args__)
        template_keys = set(PERSONALITY_TEMPLATES.keys())
        assert literal_values == template_keys, (
            f"Mismatch: in Literal but not Templates={literal_values - template_keys}, "
            f"in Templates but not Literal={template_keys - literal_values}"
        )

    def test_personality_style_is_alias_of_literal(self) -> None:
        """PersonalityStyle 应该就是 PersonalityStyleLiteral 的别名"""
        assert PersonalityStyle is PersonalityStyleLiteral

    def test_every_template_name_matches_key(self) -> None:
        """每个模板的 name 字段必须与其 dict key 一致"""
        for key, template in PERSONALITY_TEMPLATES.items():
            assert template.name == key, f"Template key '{key}' != template.name '{template.name}'"

    def test_template_count(self) -> None:
        """当前应有 17 种预置风格（8 实用 + 9 趣味）"""
        assert len(PERSONALITY_TEMPLATES) == 17


class TestPersonalityTemplateFields:
    """模板字段完整性测试"""

    @pytest.mark.parametrize("style", list(PERSONALITY_TEMPLATES.keys()))
    def test_template_has_all_required_fields(self, style: str) -> None:
        """每个模板必须有所有必要字段且非空"""
        template = PERSONALITY_TEMPLATES[style]
        assert isinstance(template, PersonalityTemplate)
        assert template.display_name, f"{style}: display_name is empty"
        assert template.display_name_zh, f"{style}: display_name_zh is empty"
        assert template.emoji, f"{style}: emoji is empty"
        assert template.system_prompt_suffix, f"{style}: system_prompt_suffix is empty"
        assert template.description, f"{style}: description is empty"
        assert template.description_zh, f"{style}: description_zh is empty"
        assert template.example_response, f"{style}: example_response is empty"

    def test_templates_are_frozen(self) -> None:
        """PersonalityTemplate 应该是不可变的"""
        template = PERSONALITY_TEMPLATES["professional"]
        with pytest.raises(AttributeError):
            template.name = "hacked"  # type: ignore[misc]


class TestQueryAPI:
    """查询 API 正确性测试"""

    def test_get_personality_template_valid(self) -> None:
        template = get_personality_template("concise")
        assert template.name == "concise"
        assert "terse" in template.system_prompt_suffix.lower()

    def test_get_personality_template_invalid_raises(self) -> None:
        with pytest.raises(KeyError):
            get_personality_template("nonexistent")  # type: ignore[arg-type]

    def test_list_all_personalities_count(self) -> None:
        all_styles = list_all_personalities()
        assert len(all_styles) == len(PERSONALITY_TEMPLATES)

    def test_list_all_personalities_type(self) -> None:
        all_styles = list_all_personalities()
        for style in all_styles:
            assert isinstance(style, PersonalityTemplate)

    def test_is_valid_personality_style_valid(self) -> None:
        assert is_valid_personality_style("professional") is True
        assert is_valid_personality_style("wenyan") is True

    def test_is_valid_personality_style_invalid(self) -> None:
        assert is_valid_personality_style("nonexistent") is False
        assert is_valid_personality_style("") is False

    def test_default_personality_style(self) -> None:
        assert DEFAULT_PERSONALITY_STYLE == "professional"
        assert is_valid_personality_style(DEFAULT_PERSONALITY_STYLE) is True


class TestConcisePromptQuality:
    """concise 模式 prompt 质量测试"""

    def test_concise_has_precise_pattern(self) -> None:
        """concise 的 prompt 应包含精确的输出模式指令"""
        template = get_personality_template("concise")
        suffix = template.system_prompt_suffix
        assert "Pattern:" in suffix, "Missing precise output pattern"

    def test_concise_has_safety_exception(self) -> None:
        """concise 的 prompt 应包含安全降级规则"""
        template = get_personality_template("concise")
        suffix = template.system_prompt_suffix
        assert "EXCEPTION" in suffix or "security" in suffix.lower(), (
            "Missing safety exception rule"
        )

    def test_concise_has_drop_list(self) -> None:
        """concise 的 prompt 应明确列出要删除的内容"""
        template = get_personality_template("concise")
        suffix = template.system_prompt_suffix
        assert "Drop:" in suffix or "drop" in suffix.lower(), "Missing explicit drop list"


class TestWenyanTemplate:
    """wenyan 文言文风格模板测试"""

    def test_wenyan_exists(self) -> None:
        assert "wenyan" in PERSONALITY_TEMPLATES

    def test_wenyan_fields(self) -> None:
        template = PERSONALITY_TEMPLATES["wenyan"]
        assert template.display_name == "Classical Chinese"
        assert template.display_name_zh == "文言文"
        assert template.emoji == "📜"

    def test_wenyan_prompt_is_chinese(self) -> None:
        """wenyan 的 prompt 应该是中文"""
        template = PERSONALITY_TEMPLATES["wenyan"]
        assert any(
            "\u4e00" <= ch <= "\u9fff" for ch in template.system_prompt_suffix
        ), "wenyan prompt should contain Chinese characters"
