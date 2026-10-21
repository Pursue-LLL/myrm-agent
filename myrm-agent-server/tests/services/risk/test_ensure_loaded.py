"""A detection engine that startup never loaded loads its rules when the first text is screened.

``init_risk_rules`` gives up after a few failed attempts; without ``ensure_loaded`` the process would then pass every
text until a restart.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.risk import detection
from app.services.risk.detection import RiskDetectionService
from app.services.risk.ingress import screen_user_text
from app.services.risk.rule_service import RiskRuleService

_SECRET_LINE = "password: Zk9#mango42"
_FACTORY = "app.platform_utils.get_session_factory"


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Store the built-in rules without loading any engine; returns how many of them start enabled."""
    async with session_factory() as db:
        service = RiskRuleService()
        await service.seed_builtin_rules(db)
        await db.commit()
        return len(await service.list_rules(db, is_enabled=True))


async def test_rules_are_loaded_from_the_database_on_first_use(session_factory: async_sessionmaker[AsyncSession]) -> None:
    enabled = await _seed(session_factory)
    assert enabled > 0
    service = RiskDetectionService()

    with patch(_FACTORY, return_value=session_factory):
        await service.ensure_loaded()

    assert service.rule_count == enabled
    assert service.version == 1


async def test_a_text_is_held_by_an_engine_that_startup_never_loaded(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(session_factory)
    service = RiskDetectionService()

    with (
        patch("app.services.risk.detection.get_detection_service", return_value=service),
        patch(_FACTORY, return_value=session_factory),
    ):
        result = await screen_user_text(_SECRET_LINE, session_id=None, record=False)

    assert result is not None and result.blocked


async def test_loaded_rules_are_not_read_again_not_even_when_there_are_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Rules that were all disabled are a loaded state: every message must not go back to the database."""
    service = RiskDetectionService()
    async with session_factory() as db:
        await service.reload(db)
    assert service.rule_count == 0

    factory = MagicMock(side_effect=AssertionError("the rules were read again"))
    with patch(_FACTORY, factory):
        await service.ensure_loaded()
        await service.ensure_loaded()

    factory.assert_not_called()


async def test_texts_arriving_together_load_the_rules_once(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _seed(session_factory)
    service = RiskDetectionService()
    reloads = 0
    reload = service.reload

    async def counted_reload(db: AsyncSession) -> int:
        nonlocal reloads
        reloads += 1
        await asyncio.sleep(0)  # lets the other callers reach the lock while this load is out
        return await reload(db)

    with patch(_FACTORY, return_value=session_factory), patch.object(service, "reload", counted_reload):
        await asyncio.gather(*(service.ensure_loaded() for _ in range(8)))

    assert reloads == 1
    assert service.rule_count > 0


async def test_a_failed_load_lets_the_text_through_logs_once_and_is_not_retried_within_the_cooldown(
    session_factory: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    await _seed(session_factory)
    service = RiskDetectionService()
    factory = MagicMock(side_effect=RuntimeError("database unavailable"))

    with patch(_FACTORY, factory), caplog.at_level(logging.WARNING, logger=detection.logger.name):
        await service.ensure_loaded()
        await service.ensure_loaded()

    assert service.rule_count == 0
    assert factory.call_count == 1
    assert [r.levelno for r in caplog.records] == [logging.ERROR]


async def test_the_rules_load_once_the_database_is_back_after_the_cooldown(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    enabled = await _seed(session_factory)
    monkeypatch.setattr(detection, "LOAD_RETRY_COOLDOWN_SECONDS", 0.0)
    service = RiskDetectionService()

    with patch(_FACTORY, side_effect=RuntimeError("database unavailable")):
        await service.ensure_loaded()
    assert service.rule_count == 0

    with patch(_FACTORY, return_value=session_factory):
        await service.ensure_loaded()
    assert service.rule_count == enabled
