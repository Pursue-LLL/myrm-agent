"""personality_templates 模块单元测试

验证模板定义的一致性、查询 API 的正确性、与 dto.py 类型定义的同步性，
以及注入块（作用域不变量 + 风格本体）的渲染契约。
"""

from __future__ import annotations

import pytest

from app.ai_agents.personality_templates import (
    DEFAULT_PERSONALITY_STYLE,
    PERSONALITY_TEMPLATES,
    STYLE_SCOPE_INVARIANT,
    PersonalityStyle,
    PersonalityTemplate,
    list_all_personalities,
    render_personality_block,
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

    def test_category_split_matches_catalog_grouping(self) -> None:
        """分类必须是 8 实用 + 9 趣味，且与前端九宫格分组一致"""
        practical = [t for t in PERSONALITY_TEMPLATES.values() if t.category == "practical"]
        fun = [t for t in PERSONALITY_TEMPLATES.values() if t.category == "fun"]
        assert len(practical) == 8
        assert len(fun) == 9

    def test_icon_ids_are_unique_and_non_empty(self) -> None:
        """GUI 图标标识必须非空且唯一，避免两个风格共用同一图标造成认知歧义"""
        icon_ids = [t.icon_id for t in PERSONALITY_TEMPLATES.values()]
        assert all(icon_id.strip() for icon_id in icon_ids)
        assert len(set(icon_ids)) == len(icon_ids)


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
        assert template.icon_id, f"{style}: icon_id is empty"
        assert template.category in ("practical", "fun"), f"{style}: invalid category"
        assert template.system_prompt_suffix, f"{style}: system_prompt_suffix is empty"
        assert template.description, f"{style}: description is empty"
        assert template.description_zh, f"{style}: description_zh is empty"
        assert template.example_response, f"{style}: example_response is empty"
        assert template.example_response_zh, f"{style}: example_response_zh is empty"

    def test_templates_are_frozen(self) -> None:
        """PersonalityTemplate 应该是不可变的"""
        template = PERSONALITY_TEMPLATES["professional"]
        with pytest.raises(AttributeError):
            template.name = "hacked"  # type: ignore[misc]


class TestQueryAPI:
    """查询 API 正确性测试"""

    def test_list_all_personalities_count(self) -> None:
        all_styles = list_all_personalities()
        assert len(all_styles) == len(PERSONALITY_TEMPLATES)

    def test_list_all_personalities_type(self) -> None:
        all_styles = list_all_personalities()
        for style in all_styles:
            assert isinstance(style, PersonalityTemplate)

    def test_default_personality_style(self) -> None:
        assert DEFAULT_PERSONALITY_STYLE == "professional"
        assert DEFAULT_PERSONALITY_STYLE in PERSONALITY_TEMPLATES


class TestConcisePromptQuality:
    """concise 模式 prompt 质量测试"""

    def _block(self) -> str:
        block = render_personality_block("concise")
        assert block is not None
        return block

    def test_concise_keeps_answer_first_pattern(self) -> None:
        """concise 的 prompt 应包含答案先行的输出结构"""
        assert "Answer first" in self._block()

    def test_concise_has_safety_exception(self) -> None:
        """concise 的注入内容必须包含安全降级规则"""
        block = self._block()
        assert "Security warnings" in block or "security warning" in block.lower()

    def test_concise_has_explicit_removal_rules(self) -> None:
        """concise 的 prompt 应明确列出要去除的内容"""
        block = self._block()
        assert "No greeting" in block
        assert "no filler words" in block

    def test_concise_preserves_decisive_words(self) -> None:
        """concise 的 prompt 必须禁止删改否定词与限定词"""
        block = self._block()
        assert "Never drop or reword" in block
        assert "not, never, no, only" in block

    def test_concise_expands_when_user_asks_for_detail(self) -> None:
        """concise 的 prompt 必须在用户要细节/重复提问时切回完整句"""
        block = self._block()
        assert "asks for an explanation or more detail" in block

    def test_concise_covers_tool_narration(self) -> None:
        """concise 的 prompt 应限制工具调用期间的旁白"""
        block = self._block()
        assert "no narration between routine calls" in block

    def test_concise_forbids_inflating_compression(self) -> None:
        """concise 的 prompt 必须禁止「越压缩越长」与自造缩写"""
        block = self._block()
        assert "not shorter than the plain phrasing" in block
        assert "No invented abbreviations" in block

    def test_concise_preserves_the_users_language(self) -> None:
        """concise 的 prompt 必须要求沿用用户语言（压缩的是风格不是语言）"""
        block = self._block()
        assert "compress the style, never the language" in block

    def test_concise_keeps_vocabulary_stable_and_plain(self) -> None:
        """concise 的 prompt 必须要求一义一词与主动语态，避免同义轮换与长句"""
        block = self._block()
        assert "Name each thing once" in block
        assert "prefer active voice" in block

    def test_concise_bounds_tool_narration_across_phases(self) -> None:
        """concise 的 prompt 必须在阶段切换时也只写一行"""
        block = self._block()
        assert "one line at each phase change" in block

    def test_injected_block_is_language_agnostic(self) -> None:
        """简洁档规则不得依赖英文文法机制，保证中文场景同样生效"""
        block = self._block()
        assert "articles" not in block.lower()
        assert "Fragments OK" not in block


class TestStyleScopeInvariant:
    """作用域不变量测试：风格只作用于聊天回复，不污染交付物，且与默认规则冲突时有裁决"""

    def test_block_carries_persisted_content_scope(self) -> None:
        block = render_personality_block("concise")
        assert block is not None
        assert STYLE_SCOPE_INVARIANT in block
        assert "files, commits, documents, memory" in block
        assert "messages to other people" in block

    def test_block_arbitrates_conflicts_with_default_rules(self) -> None:
        """风格与默认的 tone/structure/length 规则冲突时必须以风格为准，且不得牺牲准确性/完整性/安全"""
        block = render_personality_block("concise")
        assert block is not None
        assert "follow this style" in block
        assert "accuracy, completeness, and safety are never traded away" in block

    def test_default_style_injects_nothing(self) -> None:
        assert render_personality_block(DEFAULT_PERSONALITY_STYLE) is None
        assert render_personality_block(None) is None
        assert render_personality_block("") is None

    def test_unknown_style_injects_nothing(self) -> None:
        assert render_personality_block("nonexistent-style") is None

    @pytest.mark.parametrize("style", [s for s in PERSONALITY_TEMPLATES if s != DEFAULT_PERSONALITY_STYLE])
    def test_every_non_default_style_carries_invariant_and_voice(self, style: str) -> None:
        block = render_personality_block(style)
        assert block is not None
        assert block.startswith("**Communication Style**: ")
        assert STYLE_SCOPE_INVARIANT in block
        assert PERSONALITY_TEMPLATES[style].system_prompt_suffix in block


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
        assert any("\u4e00" <= ch <= "\u9fff" for ch in template.system_prompt_suffix), (
            "wenyan prompt should contain Chinese characters"
        )


class TestPromptInjectionLogic:
    """验证 personality_style 的 prompt 注入与 converter 的协作逻辑"""

    def test_non_default_style_produces_suffix(self) -> None:
        """非默认风格应产生非空的注入内容"""
        for style_name, template in PERSONALITY_TEMPLATES.items():
            if style_name == DEFAULT_PERSONALITY_STYLE:
                continue
            block = render_personality_block(style_name)
            assert block is not None
            assert "Communication Style" in block
            assert len(template.system_prompt_suffix) > 10, f"{style_name}: suffix too short"

    def test_default_style_skipped_in_injection(self) -> None:
        """默认风格 professional 在 converter 中不注入额外内容"""
        assert DEFAULT_PERSONALITY_STYLE == "professional"
        assert render_personality_block(DEFAULT_PERSONALITY_STYLE) is None

    def test_concise_block_starts_with_header(self) -> None:
        """concise 的注入内容应以统一表头开始，保持与其它入口一致的格式"""
        block = render_personality_block("concise")
        assert block is not None
        assert block.startswith("**Communication Style**: Scope:")

    @pytest.mark.parametrize("style", list(PERSONALITY_TEMPLATES.keys()))
    def test_style_voice_is_single_paragraph(self, style: str) -> None:
        """所有风格本体不应包含多余换行，避免破坏注入块结构"""
        assert "\n\n" not in PERSONALITY_TEMPLATES[style].system_prompt_suffix, (
            f"{style}: suffix contains double newline which may break prompt structure"
        )
