"""Test Knowledge Pack selector, deduplication, and proactive snippet injection.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult
- app.services.wiki.knowledge_pack.selector::KnowledgePackSelector, calculate_jaccard_similarity, resolve_proactive_snippets_from_vaults, truncate_snippet_text

[OUTPUT]
- Unit test suite verifying Jaccard dedup, hard budget truncation (600 chars), timeout fallback, and vault scanning.

[POS]
Unit test for KnowledgePackProactiveInjectionPerAgentTurn roadmap item.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.wiki.knowledge_pack.schemas import (
    KnowledgePackConfig,
    RelevantSnippet,
)
from app.services.wiki.knowledge_pack.selector import (
    KnowledgePackSelector,
    calculate_jaccard_similarity,
    resolve_proactive_snippets_from_vaults,
    truncate_snippet_text,
)


def test_jaccard_similarity_calculation() -> None:
    """Verify Jaccard token-level overlap logic."""
    assert calculate_jaccard_similarity("", "") == 0.0
    assert calculate_jaccard_similarity("hello world", "") == 0.0

    # Identical texts
    s1 = "出差住宿标准为每晚650元"
    s2 = "出差住宿标准为每晚650元"
    assert calculate_jaccard_similarity(s1, s2) == 1.0

    # Partial overlap
    s3 = "出差住宿费用标准为每晚650元实报实销"
    sim = calculate_jaccard_similarity(s1, s3)
    assert 0.5 < sim < 1.0

    # Disjoint texts
    s4 = "财务审计报销指南全流程"
    assert calculate_jaccard_similarity(s1, s4) < 0.3


def test_truncate_snippet_text() -> None:
    """Verify sentence-boundary preserving snippet truncation."""
    short = "这是简短的规则内容。"
    assert truncate_snippet_text(short, max_chars=100) == short

    long_text = "第一句话规约说明。第二句话关于差旅报销标准的详细解释说明。" + "详细规则" * 50
    truncated = truncate_snippet_text(long_text, max_chars=50)
    assert len(truncated) <= 50
    assert truncated.endswith("…") or truncated.endswith("。")


def test_selector_deduplication_and_budget() -> None:
    """Verify selector caps snippets at 3, enforces 600 chars total, and drops duplicates."""
    cfg = KnowledgePackConfig(
        pack_id="pack_test",
        name="Test Pack",
        max_snippets=3,
        max_chars_per_snippet=150,
        max_total_chars=400,
        dedup_threshold=0.70,
    )
    selector = KnowledgePackSelector(cfg)

    # 1. High confidence, unique
    c1 = RelevantSnippet(
        kb_name="HR",
        article_title="TravelPolicy",
        snippet="员工出差在深圳的住宿限额标准为每天650元，必须提前通过系统发起审批申请。",
        confidence=0.95,
    )
    # 2. Similar to c1 (should be deduplicated)
    c2 = RelevantSnippet(
        kb_name="Finance",
        article_title="Reimbursement",
        snippet="出差在深圳的住宿限额标准为每天650元，需要提前通过系统发起审批申请。",
        confidence=0.90,
    )
    # 3. High confidence, distinct
    c3 = RelevantSnippet(
        kb_name="Engineering",
        article_title="CodeReview",
        snippet="所有 Controller 层对外暴露接口必须统一封装为 APIResponse 信封模型，禁止裸抛异常。",
        confidence=0.88,
    )
    # 4. Long distinct snippet
    c4 = RelevantSnippet(
        kb_name="Ops",
        article_title="Deployment",
        snippet="生产环境发布必须在周二或者周四下午进行，且必须通过灰度发布流水线执行金丝雀验证发布流程。" * 5,
        confidence=0.85,
    )
    # 5. Extra snippet (should be truncated by max_snippets=3)
    c5 = RelevantSnippet(
        kb_name="Security",
        article_title="SecretGuard",
        snippet="禁止在代码中硬编码任何 API 密钥或凭证。",
        confidence=0.80,
    )

    res = selector.select([c1, c2, c3, c4, c5])

    # c2 must have been deduplicated
    titles = [s.article_title for s in res.snippets]
    assert "Reimbursement" not in titles
    assert "TravelPolicy" in titles
    assert "CodeReview" in titles

    # Must not exceed max_snippets
    assert len(res.snippets) <= 3

    # Must not exceed max_total_chars
    assert res.total_chars <= 400
    assert res.is_truncated is True
    assert res.source_count >= 2


@pytest.mark.asyncio
async def test_resolve_proactive_snippets_from_vaults(tmp_path: Path) -> None:
    """Verify asynchronous vault scan and fallback handling."""
    # Set up mock vault directory with markdown files
    vault_dir = tmp_path / "vault1"
    vault_dir.mkdir()
    doc_path = vault_dir / "travel_standard.md"
    doc_path.write_text(
        "# 差旅与住宿政策\n\n"
        "本指南适用于所有全职雇员。\n\n"
        "差旅住宿标准说明：深圳地区员工每晚限额 650 元人民币，凭增值税专用发票报销。\n\n"
        "日常交通补贴标准：每天封顶 80 元。\n",
        encoding="utf-8",
    )

    vault_paths = (vault_dir,)
    vault_labels = {str(vault_dir): "企业规章库"}

    # Query matching contents
    result = await resolve_proactive_snippets_from_vaults(
        query="请问深圳出差住宿标准是多少钱？",
        vault_paths=vault_paths,
        vault_labels=vault_labels,
        timeout_seconds=0.200,
    )

    assert len(result.snippets) >= 1
    top = result.snippets[0]
    assert top.kb_name == "企业规章库"
    assert "650" in top.snippet
    assert result.latency_ms >= 0.0

    # Query with empty query or non-existent path
    empty_res = await resolve_proactive_snippets_from_vaults(
        query="   ",
        vault_paths=vault_paths,
        vault_labels=vault_labels,
    )
    assert len(empty_res.snippets) == 0


@pytest.mark.asyncio
async def test_resolve_proactive_snippets_timeout_degrades_gracefully(tmp_path: Path) -> None:
    """Verify timeout guardrail safely degrades to empty snippets without failing."""
    vault_dir = tmp_path / "slow_vault"
    vault_dir.mkdir()
    (vault_dir / "doc.md").write_text("政策内容测试", encoding="utf-8")

    # Pass an ultra-short timeout (0.000001s) to force timeout branch
    result = await resolve_proactive_snippets_from_vaults(
        query="政策",
        vault_paths=(vault_dir,),
        vault_labels={str(vault_dir): "测试库"},
        timeout_seconds=0.0000001,
    )
    assert len(result.snippets) == 0


@pytest.mark.asyncio
async def test_resolve_proactive_snippets_with_fts5_index(tmp_path: Path) -> None:
    """Verify Tier 1 FTS5 index-first retrieval on compiled vault."""
    import sqlite3

    vault_dir = tmp_path / "compiled_vault"
    vault_dir.mkdir()
    db_path = vault_dir / ".wiki_index.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE VIRTUAL TABLE wiki_fts USING fts5(
                concept_name,
                truth_content,
                tokenize="unicode61 remove_diacritics 1"
            )
            """
        )
        conn.execute(
            """
            INSERT INTO wiki_fts(concept_name, truth_content)
            VALUES (?, ?)
            """,
            (
                "ExpensePolicy",
                "## 差旅报销制度\n\n全员差旅住宿标准为每晚不超过 650 元人民币。\n\n交通补贴每日上限 50 元。",
            ),
        )

    result = await resolve_proactive_snippets_from_vaults(
        query="差旅住宿标准每晚限额多少",
        vault_paths=(vault_dir,),
        vault_labels={str(vault_dir): "财务规章"},
        timeout_seconds=0.200,
    )

    assert len(result.snippets) >= 1
    assert result.snippets[0].kb_name == "财务规章"
    assert result.snippets[0].article_title == "ExpensePolicy"
    assert "650" in result.snippets[0].snippet


@pytest.mark.asyncio
async def test_resolve_proactive_snippets_with_real_wiki_concepts_dir(tmp_path: Path) -> None:
    """Verify Tier 2 fallback correctly traverses real wiki/concepts subdirectory."""
    vault_dir = tmp_path / "uncompiled_vault"
    concepts_dir = vault_dir / "wiki" / "concepts"
    concepts_dir.mkdir(parents=True)

    doc_path = concepts_dir / "code_review_guideline.md"
    doc_path.write_text(
        "# 代码规范\n\n所有对外服务接口必须统一返回 APIResponse 模型。\n\n禁止在代码中硬编码秘钥。",
        encoding="utf-8",
    )

    result = await resolve_proactive_snippets_from_vaults(
        query="对外接口返回模型规范是什么",
        vault_paths=(vault_dir,),
        vault_labels={str(vault_dir): "研发规范"},
        timeout_seconds=0.200,
    )

    assert len(result.snippets) >= 1
    assert result.snippets[0].kb_name == "研发规范"
    assert result.snippets[0].article_title == "code_review_guideline"
    assert "APIResponse" in result.snippets[0].snippet
