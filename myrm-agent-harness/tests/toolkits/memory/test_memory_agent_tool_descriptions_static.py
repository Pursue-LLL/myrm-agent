"""Static guards for memory agent tool descriptions (prompt SSOT)."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
    DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE,
    MEMORY_MANAGE_TOOL_DESCRIPTION,
    MEMORY_MANAGE_TOOL_DESCRIPTION_EN,
    MEMORY_MANAGE_TOOL_DESCRIPTION_ZH,
    MEMORY_SAVE_CORE_EN,
    MEMORY_SAVE_CORE_ZH,
    MEMORY_SAVE_WRITE_TARGET_EN,
    MEMORY_SAVE_WRITE_TARGET_ZH,
    build_memory_save_tool_description,
    build_memory_search_tool_description,
    resolve_memory_manage_tool_description,
    resolve_memory_save_tool_description,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchPolicy,
    advertised_search_corpora,
)
from myrm_agent_harness.toolkits.memory.agent_surface.wiki_memory_boundary import (
    WIKI_MEMORY_SAVE_MAX_CHARS,
    WIKI_MEMORY_SAVE_MIN_HEADINGS,
)
from myrm_agent_harness.toolkits.memory.config import MemoryConfig

_FULL_POLICY = MemorySearchPolicy(allow_wiki=True, allow_sessions=True)
_POLICIES = [
    pytest.param(MemorySearchPolicy(), id="memory-only"),
    pytest.param(MemorySearchPolicy(allow_wiki=True), id="wiki"),
    pytest.param(MemorySearchPolicy(allow_sessions=True), id="sessions"),
    pytest.param(_FULL_POLICY, id="wiki-and-sessions"),
]
_GUIDE_CORPUS_LINE = {
    "en": re.compile(r"^- ([a-z]+)(?: \(default\))?:", re.M),
    "zh": re.compile(r"^- ([a-z]+)(?:（默认）)?：", re.M),
}
_GUIDE_TITLE = {"en": "**Corpus guide**", "zh": "**Corpus 指南**"}


def test_default_locale_is_english() -> None:
    assert DEFAULT_MEMORY_TOOL_DESCRIPTION_LOCALE == "en"
    assert MEMORY_MANAGE_TOOL_DESCRIPTION is MEMORY_MANAGE_TOOL_DESCRIPTION_EN
    assert resolve_memory_save_tool_description() == build_memory_save_tool_description(
        MemorySearchPolicy(), locale="en"
    )
    assert resolve_memory_manage_tool_description() == MEMORY_MANAGE_TOOL_DESCRIPTION_EN


@pytest.mark.parametrize(
    ("locale", "core", "write_target"),
    [
        pytest.param("en", MEMORY_SAVE_CORE_EN, MEMORY_SAVE_WRITE_TARGET_EN, id="en"),
        pytest.param("zh", MEMORY_SAVE_CORE_ZH, MEMORY_SAVE_WRITE_TARGET_ZH, id="zh"),
    ],
)
def test_write_target_block_follows_the_core_only_while_shared_writes_are_allowed(
    locale: str, core: str, write_target: str
) -> None:
    assert build_memory_save_tool_description(MemorySearchPolicy(), locale=locale) == f"{core}\n\n{write_target}"
    blocked = MemorySearchPolicy(allow_shared_write=False)
    assert build_memory_save_tool_description(blocked, locale=locale) == core


def test_mcp_surface_maps_gui_tool_names() -> None:
    manage_mcp = resolve_memory_manage_tool_description(surface="mcp")
    assert "memory_recall" in manage_mcp
    assert "memory_store" in manage_mcp
    assert "memory_search_tool" not in manage_mcp
    assert "memory_save_tool" not in manage_mcp

    store_mcp = build_memory_save_tool_description(
        MemorySearchPolicy(allow_wiki=True),
        surface="mcp",
    )
    assert "memory_manage" in store_mcp
    assert "memory_save_tool" not in store_mcp
    assert "corpus=" not in store_mcp
    assert "WIKI BOUNDARY" in store_mcp
    assert "wiki_ingest_tool" not in store_mcp


def test_mcp_surface_zh_never_leaks_gui_wiki_tool() -> None:
    """Chinese MCP surface must never reference the GUI-only wiki_ingest_tool.

    Covers both the default description and the explicit wiki-enabled safety
    net (the WIKI BOUNDARY fragment is authored per surface).
    """
    from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
        build_mcp_memory_store_tool_description,
    )

    default_zh = build_mcp_memory_store_tool_description(locale="zh")
    assert "wiki_ingest_tool" not in default_zh

    wiki_enabled_zh = build_mcp_memory_store_tool_description(
        wiki_boundary_in_description=True,
        locale="zh",
    )
    assert "wiki_ingest_tool" not in wiki_enabled_zh
    assert "Wiki 边界" in wiki_enabled_zh
    assert "长文/笔记/参考资料不属于 memory" in wiki_enabled_zh


def test_memory_tool_descriptions_preserve_guardrails_en() -> None:
    save = build_memory_save_tool_description(MemorySearchPolicy(), locale="en")
    manage = MEMORY_MANAGE_TOOL_DESCRIPTION_EN
    search = build_memory_search_tool_description(MemorySearchPolicy(), locale="en")
    assert "**WHEN TO SAVE**" in save
    assert "do this proactively" in save
    assert "memory_manage_tool" in save
    assert "corpus=" not in save
    assert "do not set rule_trigger" in save
    assert "**CATEGORY GUIDE**" in save
    assert "one standalone declarative fact per entry" in save
    assert "**ATTRIBUTION & TRANSIENT STATES**" in save
    assert "**WHEN TO USE**" in manage
    assert "memory_save_tool" in manage
    assert "memory_search_tool" in manage
    assert "knowledge memories only" in manage
    assert "preserves history" in manage
    assert "preference_key" in manage
    assert "category" not in manage
    assert "release the protection first" in manage
    assert "corpus=" not in manage
    assert "profile_key" in search


def test_memory_tool_descriptions_preserve_guardrails_zh() -> None:
    save = build_memory_save_tool_description(MemorySearchPolicy(), locale="zh")
    manage = MEMORY_MANAGE_TOOL_DESCRIPTION_ZH
    search = build_memory_search_tool_description(MemorySearchPolicy(), locale="zh")
    assert "**何时保存**" in save
    assert "memory_manage_tool" in save
    assert "corpus=" not in save
    assert "不要设置 rule_trigger" in save
    assert "**类别指南**" in save
    assert "一条可独立理解的陈述性事实" in save
    assert "**归属与短暂状态**" in save
    assert "长期或慢性状况" in save
    assert "**何时使用**" in manage
    assert "memory_save_tool" in manage
    assert "仅 knowledge 记忆" in manage
    assert "保留历史记录" in manage
    assert "preference_key" in manage
    assert "category" not in manage
    assert "请先请用户解除保护" in manage
    assert "corpus=" not in manage
    assert "profile_key" in search


@pytest.mark.parametrize(
    ("locale", "marker", "scope", "other_categories"),
    [
        pytest.param("en", "**IMPORTANCE**", "knowledge only", ("preference", "rule", "behavior"), id="en"),
        pytest.param("zh", "**重要性**", "仅 knowledge", ("偏好", "规则", "行为"), id="zh"),
    ],
)
def test_the_importance_rubric_scores_only_knowledge(
    locale: str, marker: str, scope: str, other_categories: tuple[str, ...]
) -> None:
    """Only a knowledge save reads ``importance``.

    A rubric that scores preferences or corrected behavior invites values nothing reads.
    """
    from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
        build_mcp_memory_store_tool_description,
    )

    descriptions = {
        "agent": build_memory_save_tool_description(MemorySearchPolicy(), locale=locale),
        "mcp": build_mcp_memory_store_tool_description(locale=locale),
    }
    for surface, description in descriptions.items():
        rubric = description.split(marker, 1)[1].split("\n\n", 1)[0]
        assert scope in rubric, surface
        assert not [word for word in other_categories if word in rubric], surface


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_write_tool_texts_never_point_at_the_schema(locale: str) -> None:
    """A description states what the schema does not say; it never points at the schema or repeats its enum."""
    texts = (
        build_memory_save_tool_description(MemorySearchPolicy(), locale=locale),
        resolve_memory_manage_tool_description(locale),
    )
    for text in texts:
        assert "Parameter semantics" not in text
        assert "参数说明见" not in text


def test_write_tool_schemas_never_point_back_at_the_description() -> None:
    from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.manage_tool import MemoryManageInput
    from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.save_tool import MemorySaveInput

    for model in (MemorySaveInput, MemoryManageInput):
        for name, spec in model.model_json_schema()["properties"].items():
            description = str(spec.get("description", ""))
            assert "see tool description" not in description, name
            assert "see description" not in description, name


def test_memory_save_description_omits_wiki_boundary_when_disabled() -> None:
    desc = build_memory_save_tool_description(MemorySearchPolicy(), locale="en")
    assert "wiki_ingest_tool" not in desc
    assert "WIKI BOUNDARY" not in desc


def test_memory_save_description_includes_wiki_boundary_when_enabled() -> None:
    desc = build_memory_save_tool_description(
        MemorySearchPolicy(allow_wiki=True),
        locale="en",
    )
    assert "wiki_ingest_tool" in desc
    assert str(WIKI_MEMORY_SAVE_MAX_CHARS) in desc
    assert str(WIKI_MEMORY_SAVE_MIN_HEADINGS) in desc


def test_memory_save_description_includes_approval_when_required() -> None:
    desc = build_memory_save_tool_description(
        MemorySearchPolicy(),
        approval_required=True,
        locale="en",
    )
    assert "submitted for approval" in desc


def test_create_memory_tools_uses_description_ssot(
    memory_config: MemoryConfig, mock_vector_store: AsyncMock, mock_embedding: AsyncMock
) -> None:
    from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import (
        create_memory_tools,
    )
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    manager = MemoryManager(
        memory_config,
        user_id="test-user",
        vector=mock_vector_store,
        embedding=mock_embedding,
    )
    tools = create_memory_tools(manager)
    by_name = {tool.name: tool for tool in tools}
    expected_save = build_memory_save_tool_description(
        MemorySearchPolicy(),
        approval_required=manager.approval_required,
        locale="en",
    )
    assert by_name["memory_save_tool"].description == expected_save
    assert by_name["memory_manage_tool"].description == MEMORY_MANAGE_TOOL_DESCRIPTION_EN
    assert by_name["memory_search_tool"].description == build_memory_search_tool_description(
        MemorySearchPolicy(), locale="en"
    )


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("policy", _POLICIES)
def test_search_description_guide_lists_exactly_the_advertised_corpora(policy: MemorySearchPolicy, locale: str) -> None:
    desc = build_memory_search_tool_description(policy, locale=locale)
    advertised = list(advertised_search_corpora(policy))
    guide_corpora = _GUIDE_CORPUS_LINE[locale].findall(desc)
    if len(advertised) == 1:
        assert _GUIDE_TITLE[locale] not in desc
        assert guide_corpora == []
        assert "corpus=" not in desc
    else:
        assert _GUIDE_TITLE[locale] in desc
        assert guide_corpora == advertised


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("policy", _POLICIES)
def test_search_description_names_conversation_search_only_when_sessions_are_enabled(
    policy: MemorySearchPolicy, locale: str
) -> None:
    desc = build_memory_search_tool_description(policy, locale=locale)
    conversation_terms = ("corpus=sessions", "expand_conversation_id", "expand_message_id", "message_id")
    assert all(term in desc for term in conversation_terms) is policy.allow_sessions
    assert any(term in desc for term in conversation_terms) is policy.allow_sessions


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("policy", _POLICIES)
def test_search_description_never_contradicts_the_corpus_choice(policy: MemorySearchPolicy, locale: str) -> None:
    desc = build_memory_search_tool_description(policy, locale=locale)
    assert "- web" not in desc
    assert "corpus=web" not in desc
    assert "For memory retrieval only" not in desc
    assert "仅用于记忆检索" not in desc


def test_search_description_carries_the_sessions_routing_triggers() -> None:
    en = build_memory_search_tool_description(_FULL_POLICY, locale="en")
    for trigger in ("last time", "previously", "continue that discussion", "branch/fork"):
        assert trigger in en
    zh = build_memory_search_tool_description(_FULL_POLICY, locale="zh-CN")
    for trigger in ("上次", "之前", "接着聊", "分支/fork"):
        assert trigger in zh
    assert "Wiki 文档" in zh
    assert "历史会话" in zh


def test_memory_tool_descriptions_support_zh_cn_locale() -> None:
    assert resolve_memory_save_tool_description("zh-CN") == build_memory_save_tool_description(
        MemorySearchPolicy(), locale="zh-CN"
    )
    assert resolve_memory_manage_tool_description("zh-CN") == MEMORY_MANAGE_TOOL_DESCRIPTION_ZH
    search = build_memory_search_tool_description(_FULL_POLICY, locale="zh-CN")
    assert "**Corpus 指南**" in search


def test_create_memory_tools_supports_chinese_locale(
    memory_config: MemoryConfig, mock_vector_store: AsyncMock, mock_embedding: AsyncMock
) -> None:
    from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import (
        create_memory_tools,
    )
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    manager = MemoryManager(
        memory_config,
        user_id="test-user",
        vector=mock_vector_store,
        embedding=mock_embedding,
    )
    tools = create_memory_tools(manager, description_locale="zh-CN")
    by_name = {tool.name: tool for tool in tools}
    expected_save = build_memory_save_tool_description(
        MemorySearchPolicy(),
        approval_required=manager.approval_required,
        locale="zh-CN",
    )
    assert by_name["memory_save_tool"].description == expected_save
    assert by_name["memory_manage_tool"].description == MEMORY_MANAGE_TOOL_DESCRIPTION_ZH
    assert by_name["memory_search_tool"].description == build_memory_search_tool_description(
        MemorySearchPolicy(), locale="zh"
    )
