"""Unit tests for Feishu contact fuzzy matcher and disambiguation engine."""

from app.channels.providers.feishu.cards import (
    build_contact_disambiguation_card,
)
from app.channels.providers.feishu.contact_fuzzy import (
    FeishuContactFuzzyMatcher,
    calculate_name_similarity,
)


def test_calculate_name_similarity_exact_and_phonetic() -> None:
    """Test exact match and homophone phonetic similarity."""
    # Exact match
    assert calculate_name_similarity("张婷", "张婷") == 1.0
    assert calculate_name_similarity("zhangting", "zhangting") == 1.0

    # Homophone near-match (张廷 vs 张婷)
    sim_homophone = calculate_name_similarity("张廷", "张婷")
    assert sim_homophone >= 0.85

    # Near match (王玮 vs 王伟)
    sim_homophone_2 = calculate_name_similarity("王玮", "王伟")
    assert sim_homophone_2 >= 0.85

    # Completely different
    sim_diff = calculate_name_similarity("李雷", "韩梅梅")
    assert sim_diff < 0.40


def test_feishu_contact_fuzzy_matcher_single_confident_match() -> None:
    """Test single high-confidence match without disambiguation."""
    directory = [
        {"open_id": "ou_001", "name": "张婷", "department": "市场部", "email": "zt@co.com"},
        {"open_id": "ou_002", "name": "李强", "department": "技术部", "email": "lq@co.com"},
        {"open_id": "ou_003", "name": "王伟", "department": "销售部", "email": "ww@co.com"},
    ]
    matcher = FeishuContactFuzzyMatcher(directory)

    # Search with typo '张廷'
    result = matcher.match("张廷")
    assert result.is_confident_match is True
    assert result.requires_disambiguation is False
    assert result.best_match is not None
    assert result.best_match.open_id == "ou_001"
    assert result.best_match.name == "张婷"


def test_feishu_contact_fuzzy_matcher_disambiguation_required() -> None:
    """Test multiple close candidate matches requiring disambiguation card."""
    directory = [
        {"open_id": "ou_001", "name": "王伟", "department": "销售一部", "email": "ww1@co.com"},
        {"open_id": "ou_002", "name": "王伟", "department": "技术二部", "email": "ww2@co.com"},
        {"open_id": "ou_003", "name": "王玮", "department": "市场部", "email": "ww3@co.com"},
    ]
    matcher = FeishuContactFuzzyMatcher(directory)

    # Search '王伟'
    result = matcher.match("王伟")
    assert result.requires_disambiguation is True
    assert result.is_confident_match is False
    assert len(result.candidates) >= 2


def test_feishu_contact_fuzzy_matcher_department_hint_boost() -> None:
    """Test department hint boosts relevant candidate to confident match."""
    directory = [
        {"open_id": "ou_001", "name": "李伟", "department": "销售部", "email": "lw1@co.com"},
        {"open_id": "ou_002", "name": "李伟", "department": "技术研发部", "email": "lw2@co.com"},
    ]
    matcher = FeishuContactFuzzyMatcher(directory)

    # Search with department hint
    result = matcher.match("李伟", department_hint="研发")
    assert result.is_confident_match is True
    assert result.best_match is not None
    assert result.best_match.open_id == "ou_002"


def test_build_contact_disambiguation_card() -> None:
    """Test interactive disambiguation card generation."""
    candidates = [
        {"open_id": "ou_001", "name": "张婷", "department": "市场部"},
        {"open_id": "ou_002", "name": "张廷", "department": "财务部"},
    ]
    card = build_contact_disambiguation_card("张廷", candidates)
    assert card["header"]["title"]["content"] == "联系人确认 (Contact Disambiguation)"
    elements = card.get("elements", [])
    assert len(elements) == 2
    actions = elements[1]["actions"]
    assert len(actions) == 2
    assert "张婷 (市场部)" in actions[0]["text"]["content"]


def test_build_deliverable_card() -> None:
    """Test deliverable handover card generation."""
    card = build_deliverable_card(
        "Q3季度销售ROI总结报告",
        "已由 AI 助手在沙箱中完成 PPT 制作与 Bitable 多维表格建表。",
        file_name="Q3_Sales_ROI.pptx",
        file_url="https://feishu.cn/file/f_123",
        bitable_url="https://feishu.cn/base/b_456",
    )
    assert card["header"]["title"]["content"] == "💼 工作交付成果 (Deliverable Handoff)"
    elements = card.get("elements", [])
    assert len(elements) == 2
    actions = elements[1]["actions"]
    assert len(actions) == 2
    assert actions[0]["url"] == "https://feishu.cn/file/f_123"
    assert actions[1]["url"] == "https://feishu.cn/base/b_456"
