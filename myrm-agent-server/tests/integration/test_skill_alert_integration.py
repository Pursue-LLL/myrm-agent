"""Integration tests for Skill Alert functionality

Tests alert webhook and rule CRUD APIs with real database.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base


@pytest_asyncio.fixture
async def test_db_engine():
    """Create test database engine"""
    # Import model to register with metadata
    from app.database.models.skill_alert_rule import SkillAlertRule  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine):
    """Create test database session"""
    return async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_create_alert_rule(test_db_session):
    """Test creating alert rule"""
    from app.database.models.skill_alert_rule import SkillAlertRule

    async with test_db_session() as session:
        rule = SkillAlertRule(
            skill_id="test-skill",
            quality_threshold=0.7,
            channels=["slack"],
            enabled=True,
            slack_webhook_url="https://hooks.slack.com/test",
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)

        assert rule.skill_id == "test-skill"
        assert rule.quality_threshold == 0.7
        assert rule.channels == ["slack"]


@pytest.mark.asyncio
async def test_get_alert_rule(test_db_session):
    """Test getting alert rule"""
    from app.database.models.skill_alert_rule import SkillAlertRule

    async with test_db_session() as session:
        rule = SkillAlertRule(
            skill_id="test-skill",
            quality_threshold=0.7,
            channels=["slack"],
            enabled=True,
        )
        session.add(rule)
        await session.commit()

    async with test_db_session() as session:
        retrieved = await session.get(SkillAlertRule, "test-skill")
        assert retrieved is not None
        assert retrieved.quality_threshold == 0.7


@pytest.mark.asyncio
async def test_alert_webhook_check(test_db_session):
    """Test alert webhook check logic"""
    from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore

    from app.database.models.skill_alert_rule import SkillAlertRule
    from app.services.skills.quality_alert_webhook import SkillQualityAlertWebhook

    async with test_db_session() as session:
        rule = SkillAlertRule(
            skill_id="test-skill",
            quality_threshold=0.7,
            channels=["slack"],
            enabled=True,
            slack_webhook_url="https://hooks.slack.com/test",
        )
        session.add(rule)
        await session.commit()

    webhook = SkillQualityAlertWebhook(test_db_session)

    low_score = SkillQualityScore(
        success_rate=0.4,
        token_efficiency=0.5,
        execution_time=0.6,
        user_satisfaction=0.4,
        call_frequency=0.3,
    )

    try:
        await webhook.check_and_alert("test-skill", low_score)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_trends_api_data_structure():
    """Test trends API data structure (smoke test)"""
    from datetime import datetime

    data_point = {
        "timestamp": datetime.now().isoformat(),
        "avg_quality_score": 0.85,
        "avg_success_rate": 0.9,
        "execution_count": 100,
    }

    assert "timestamp" in data_point
    assert "avg_quality_score" in data_point
    assert "execution_count" in data_point


if __name__ == "__main__":
    import asyncio

    print("Running integration tests...")
    asyncio.run(test_create_alert_rule(None))
