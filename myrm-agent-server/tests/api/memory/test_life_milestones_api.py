"""Integration tests for Life Milestones and Personal Timeline API.

[POS]
Integration tests verifying life milestone registration, timeline querying,
era management, value system evolution, growth diaries, and empathetic projections.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.life_milestones_router (router)
- app.services.memory.life_milestones.provider (reset_life_milestones_suite)

[OUTPUT]
- Test functions covering life milestones API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.life_milestones_router import (
    router as life_milestones_router,
)
from app.services.memory.life_milestones.provider import (
    reset_life_milestones_suite,
)


@pytest.fixture(autouse=True)
def reset_suite_before_test() -> None:
    """Reset suite before each test to guarantee fresh seed state."""
    reset_life_milestones_suite()


@pytest.fixture
def test_app() -> FastAPI:
    """Create FastAPI test application with life milestones router."""
    api_app = FastAPI()
    api_app.include_router(life_milestones_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_record_and_get_milestone(test_app: FastAPI) -> None:
    """Verify recording, retrieving, and gate-filtering of life milestones."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Record genuine milestone
        resp = await client.post(
            "/api/memory/life-milestones/milestone",
            json={
                "timestamp_str": "2022-05-18",
                "year": 2022,
                "category": "education",
                "title": "获得全日制硕士学位",
                "narrative": "顺利完成了高级计算机体系结构课题研究并答辩通过",
                "long_term_impact": "为日后的底层引擎架构设计打下坚实学术根基",
                "core_values": ["求真", "精进"],
                "intimacy_level": "open_overview",
                "significance_score": 0.88,
                "location": "北京",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "获得全日制硕士学位"
        ms_id = data["milestone_id"]

        # 2. Get milestone
        get_resp = await client.get(f"/api/memory/life-milestones/milestone/{ms_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["location"] == "北京"

        # 3. Industrial trivia should be rejected by significance gate
        bad_resp = await client.post(
            "/api/memory/life-milestones/milestone",
            json={
                "timestamp_str": "2024-01-01",
                "year": 2024,
                "category": "career",
                "title": "修复了一个关于 CSS 样式的 bug",
                "narrative": "调整了按钮 margin 并执行单测",
                "long_term_impact": "修复了页面显示问题",
                "is_user_explicit": False,
            },
        )
        assert bad_resp.status_code == 400
        assert "significance gate" in bad_resp.json()["detail"]


@pytest.mark.asyncio
async def test_timeline_and_eras_query(test_app: FastAPI) -> None:
    """Verify chronological timeline retrieval and era management."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Query timeline with seed data
        resp = await client.get(
            "/api/memory/life-milestones/timeline",
            params={"max_intimacy": "intimate_personal"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 2
        # Verify chronological order
        years = [item["year"] for item in items]
        assert years == sorted(years)

        # 2. Register a new life stage era
        era_resp = await client.post(
            "/api/memory/life-milestones/era",
            json={
                "era_id": "era_future_horizon",
                "label": "全球视野与数智探索期",
                "start_year": 2026,
                "end_year": None,
                "guiding_philosophy": "构建造福全人类的终身智能伴侣",
            },
        )
        assert era_resp.status_code == 201

        # 3. List all eras
        list_eras_resp = await client.get("/api/memory/life-milestones/eras")
        assert list_eras_resp.status_code == 200
        era_ids = [e["era_id"] for e in list_eras_resp.json()]
        assert "era_future_horizon" in era_ids


@pytest.mark.asyncio
async def test_value_system_evolution_and_context_projection(test_app: FastAPI) -> None:
    """Verify value system registration, evolution, and prompt context projection."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Register value
        val_resp = await client.post(
            "/api/memory/life-milestones/value-node",
            json={
                "theme": "风险偏好",
                "current_stance": "审慎稳健，以核心基本盘为先",
                "effective_since_year": 2023,
                "weight": 1.4,
            },
        )
        assert val_resp.status_code == 201
        prior_id = val_resp.json()["value_id"]

        # 2. Evolve value
        evolve_resp = await client.post(
            "/api/memory/life-milestones/value-node/evolve",
            json={
                "prior_value_id": prior_id,
                "theme": "风险偏好",
                "new_stance": "杠铃策略：90%资产追求极致安全，10%拥抱高成长非对称机会",
                "transition_catalyst": "通过多次市场周期历练，理解了反脆弱的核心本质",
                "effective_since_year": 2024,
            },
        )
        assert evolve_resp.status_code == 200
        evolved_data = evolve_resp.json()
        assert "杠铃策略" in evolved_data["current_stance"]

        # 3. Project context for deep life choices
        proj_resp = await client.post(
            "/api/memory/life-milestones/project-context",
            json={
                "query_text": "在考虑是否要离开现在稳定的环境去全职创业，内心比较纠结与焦虑",
                "max_intimacy": "intimate_personal",
            },
        )
        assert proj_resp.status_code == 200
        bundle = proj_resp.json()
        assert bundle["relevant_milestone_count"] > 0
        assert "用户生命历程与核心价值观坐标" in bundle["projected_text"]
        assert "回复原则" in bundle["projected_text"]


@pytest.mark.asyncio
async def test_growth_diary_and_retrospective_card_and_stats(test_app: FastAPI) -> None:
    """Verify personal diary reflections, card generation, and telemetry stats."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Record diary
        diary_resp = await client.post(
            "/api/memory/life-milestones/diary",
            json={
                "emotional_state": "释然感恩",
                "reflection_text": "回望走过的十年，很多看似挫败的经历原来都是人生最宝贵的馈赠，内心充满宁静与感激。",
                "era_label": "成家立业与长期主义期",
            },
        )
        assert diary_resp.status_code == 201

        # 2. Generate retrospective card
        card_resp = await client.get(
            "/api/memory/life-milestones/retrospective-card",
            params={"era_label": "成家立业与长期主义期", "start_year": 2023},
        )
        assert card_resp.status_code == 200
        card = card_resp.json()
        assert card["era_label"] == "成家立业与长期主义期"
        assert len(card["milestone_highlights"]) > 0
        assert "伴侣" in card["companion_empathy_note"] or "陪伴" in card["companion_empathy_note"]

        # 3. Telemetry stats
        stats_resp = await client.get("/api/memory/life-milestones/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_milestones"] >= 3
        assert stats["total_eras"] >= 3
        assert stats["active_values"] >= 1
        assert stats["total_diaries"] >= 2
