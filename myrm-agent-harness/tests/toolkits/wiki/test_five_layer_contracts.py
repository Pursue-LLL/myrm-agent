"""Unit tests for Five-Layer Wiki structure, SourceCardContract, and RadarRationaleContract."""

import tempfile

from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
    WikiPageType,
)
from myrm_agent_harness.toolkits.wiki.core.radar_rationale_contract import (
    ZeroYieldRationaleReport,
    format_zero_yield_report,
    parse_zero_yield_report,
)
from myrm_agent_harness.toolkits.wiki.core.source_card_contract import (
    SourceCardContract,
    parse_source_card,
    serialize_source_card,
)
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure


def test_five_layer_wiki_structure_ensure_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        structure = WikiStructure(base_dir=tmpdir)
        structure.ensure_structure()

        assert structure.raw_dir.is_dir()
        assert structure.sources_dir.is_dir()
        assert structure.wiki_dir.is_dir()
        assert structure.concepts_dir.is_dir()
        assert structure.claims_dir.is_dir()
        assert structure.methods_dir.is_dir()
        assert structure.templates_dir.is_dir()
        assert structure.deliverables_dir.is_dir()
        assert structure.inbox_dir.is_dir()
        assert structure.archive_dir.is_dir()

        # Path getters
        src_path = structure.get_source_file_path("src_paper_2026")
        assert src_path.parent == structure.sources_dir
        assert src_path.name == "src-paper-2026.md"

        deliv_path = structure.get_deliverable_file_path("bank_proposal.md")
        assert deliv_path.parent == structure.deliverables_dir

        claim_path = structure.get_claim_file_path("author_viewpoint")
        assert claim_path.parent == structure.claims_dir


def test_frontmatter_page_types_extended():
    assert WikiPageType.CLAIM == "claim"
    assert WikiPageType.METHOD == "method"
    assert WikiPageType.TEMPLATE == "template"
    assert WikiPageType.DELIVERABLE == "deliverable"


def test_source_card_serialization_and_parsing():
    card = SourceCardContract(
        source_id="src_workbuddy_guide",
        title="我是如何用WorkBuddy搭建AI培训知识库的",
        author="智见AI",
        platform="wechat",
        url_or_path="https://mp.weixin.qq.com/s/sample",
        provenance_class="author_claim",
        risk_level="medium",
        covered_concepts=["five_layer_wiki", "claim_separation"],
        verification_notes="详细验证了事实与主张分离对减少幻觉的关键作用",
    )

    content = serialize_source_card(card, body_markdown="这是正文中的备注内容")
    assert "source_id: src_workbuddy_guide" in content
    assert "provenance_class: author_claim" in content
    assert "这是正文中的备注内容" in content

    parsed = parse_source_card(content)
    assert parsed.source_id == "src_workbuddy_guide"
    assert parsed.author == "智见AI"
    assert parsed.provenance_class == "author_claim"
    assert "five_layer_wiki" in parsed.covered_concepts
    assert "这是正文中的备注内容" in parsed.verification_notes


def test_radar_zero_yield_report():
    report = ZeroYieldRationaleReport(
        batch_id="batch_20260923_01",
        query_topic="量子计算实用化常温超导进展",
        executed_at="2026-09-23T10:00:00Z",
        deep_research_candidates=12,
        report_candidates=5,
        web_baseline_candidates=30,
        yield_decision="zero_yield_suppressed",
        rationale="所检索到的 47 项候选结果均为营销号与无对照实验之个人揣测，缺乏可复现实验依据。",
        suggested_next_probe="等待权威期刊 Nature / Science 发文后再行探测。",
    )

    markdown = format_zero_yield_report(report)
    assert "宁缺毋滥，拦截入库 (zero_yield_suppressed)" in markdown
    assert "量子计算实用化常温超导进展" in markdown

    parsed = parse_zero_yield_report(markdown)
    assert parsed.batch_id == "batch_20260923_01"
    assert parsed.yield_decision == "zero_yield_suppressed"
    assert parsed.deep_research_candidates == 12
    assert "营销号" in parsed.rationale
