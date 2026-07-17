"""Unit tests for skill growth query helpers (merge limit and SQL status counts)."""

from __future__ import annotations

from uuid import uuid4

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base
from app.platform_utils import get_database_engine, reset_database_engine
from app.services.skills.evolution_reviews import create_evolution_review_record
from app.services.skills.growth_case_types import SkillGrowthCaseStatus
from app.services.skills.growth_queries import (
    SkillGrowthDashboardStatsRead,
    _count_cases_for_statuses,
    _count_skill_growth_cases,
    _merge_fetch_limit,
    get_skill_growth_case_detail,
    list_skill_growth_cases,
    summarize_skill_growth_dashboard_stats,
)
from app.services.skills.draft_notification import notify_skill_draft_created


@pytest.fixture
async def setup_database() -> None:
    await reset_database_engine()
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ApprovalRecord))
        await db.commit()
    await reset_database_engine()


def test_merge_fetch_limit_uses_limit_plus_offset() -> None:
    assert _merge_fetch_limit(limit=50, offset=100) == 150
    assert _merge_fetch_limit(limit=1, offset=0) == 1


@pytest.mark.asyncio
async def test_summarize_dashboard_stats_empty() -> None:
    with patch(
        "app.services.skills.growth_queries._count_skill_growth_cases",
        AsyncMock(return_value=0),
    ):
        stats = await summarize_skill_growth_dashboard_stats()

    assert stats == SkillGrowthDashboardStatsRead(
        total=0,
        pending_review=0,
        auto_applied=0,
        blocked=0,
    )


@pytest.mark.asyncio
async def test_summarize_dashboard_stats_buckets() -> None:
    with (
        patch(
            "app.services.skills.growth_queries._count_skill_growth_cases",
            AsyncMock(return_value=4),
        ),
        patch(
            "app.services.skills.growth_queries._count_cases_for_statuses",
            AsyncMock(side_effect=[2, 1, 1]),
        ),
    ):
        stats = await summarize_skill_growth_dashboard_stats()

    assert stats.total == 4
    assert stats.pending_review == 2
    assert stats.auto_applied == 1
    assert stats.blocked == 1


@pytest.mark.asyncio
async def test_sql_status_counts_and_list_total(setup_database: None) -> None:
    await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": f"growth_queries_{uuid4().hex}",
            "type": "skill_draft",
            "skill_name": "growth-queries-draft",
            "skill_description": "Draft for SQL count regression",
            "trigger_condition": "When counting",
            "skill_steps": "1. Count",
        }
    )
    await create_evolution_review_record(
        agent_id="growth-queries-test",
        chat_id=None,
        proposal_skill_id="growth-queries-evolution",
        skill_name="growth-queries-evolution",
        skill_path="/tmp/growth-queries-evolution.md",
        evolution_type="fix",
        reason="Evolution for SQL count regression",
        original_content="def before():\n    pass\n",
        evolved_content="def before():\n    return 1\n",
        confidence=0.75,
        test_passed=True,
        task_context="growth queries regression",
    )

    total = await _count_skill_growth_cases(status=None)
    pending = await _count_cases_for_statuses(
        {SkillGrowthCaseStatus.PENDING_REVIEW, SkillGrowthCaseStatus.APPLY_FAILED},
    )
    assert total >= 2
    assert pending >= 2

    stats = await summarize_skill_growth_dashboard_stats()
    assert stats.total == total
    assert stats.pending_review == pending

    items, list_total = await list_skill_growth_cases(limit=1, offset=0)
    assert list_total == total
    assert len(items) == 1

    pending_only, pending_total = await list_skill_growth_cases(
        limit=50,
        offset=0,
        status=SkillGrowthCaseStatus.PENDING_REVIEW,
    )
    assert pending_total >= 2
    assert all(item.status == SkillGrowthCaseStatus.PENDING_REVIEW for item in pending_only)

    missing_detail = await get_skill_growth_case_detail("draft:missing-case-id")
    assert missing_detail is None

    if list_total >= 2:
        second_page, _ = await list_skill_growth_cases(limit=1, offset=1)
        assert len(second_page) == 1
        assert second_page[0].id != items[0].id
