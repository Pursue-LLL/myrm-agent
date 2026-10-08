"""Startup risk-rule initialization against a real SQLite engine.

Seeding reads before it writes. When another startup task commits in between, SQLite aborts the seed's write
at once with "database is locked" (SQLITE_BUSY_SNAPSHOT, which ``busy_timeout`` does not cover). The detection
engine must then still get its rules: ``init_risk_rules`` retries on a fresh transaction.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.factory import register_sqlite_transaction_events
from app.database.models import RiskRule
from app.lifecycle import risk_rules
from app.services.risk.constants import builtin_risk_rules
from app.services.risk.detection import RiskDetectionService
from app.services.risk.rule_service import RiskRuleService

_LOGGER_NAME = "app.lifecycle.risk_rules"
_LOCKED = OperationalError("INSERT INTO risk_rules", {}, sqlite3.OperationalError("database is locked"))


def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=300")
    cursor.close()


@pytest.fixture()
async def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk.db'}",
        future=True,
        connect_args={"check_same_thread": False},
        pool_size=3,
        max_overflow=1,
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    async with engine.begin() as conn:
        await conn.run_sync(RiskRule.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: factory)
    monkeypatch.setattr(risk_rules, "_RISK_RULE_INIT_RETRY_DELAY_SEC", 0)
    yield factory
    await engine.dispose()


@pytest.fixture()
def detection(monkeypatch: pytest.MonkeyPatch) -> RiskDetectionService:
    service = RiskDetectionService()
    monkeypatch.setattr("app.services.risk.detection.get_detection_service", lambda: service)
    return service


async def _stored_rule_count(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as db:
        return (await db.execute(select(func.count()).select_from(RiskRule))).scalar_one()


@pytest.mark.asyncio
async def test_a_competing_startup_writer_does_not_leave_the_engine_without_rules(
    session_factory: async_sessionmaker[AsyncSession],
    detection: RiskDetectionService,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed = RiskRuleService.seed_builtin_rules
    attempts = 0

    async def seed_after_a_competing_commit(service: RiskRuleService, session: AsyncSession) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await session.execute(select(func.count()).select_from(RiskRule))  # pins the snapshot, as the seed's own read does
            async with session_factory() as other:
                other.add(RiskRule(rule_id="other-startup-writer", display_name="x", pattern="x", severity="low", action="allow"))
                await other.commit()
        return await seed(service, session)

    monkeypatch.setattr(RiskRuleService, "seed_builtin_rules", seed_after_a_competing_commit)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        await risk_rules.init_risk_rules()

    stored = await _stored_rule_count(session_factory)
    assert attempts == 2
    assert stored == len(builtin_risk_rules()) + 1
    assert detection.rule_count == stored
    assert "locked database (attempt 1)" in caplog.text
    assert "initialization failed" not in caplog.text


@pytest.mark.asyncio
async def test_a_database_that_stays_locked_is_reported_once_after_every_attempt(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    async def always_locked() -> None:
        nonlocal attempts
        attempts += 1
        raise _LOCKED

    monkeypatch.setattr(risk_rules, "_seed_and_load_risk_rules", always_locked)
    monkeypatch.setattr(risk_rules, "_RISK_RULE_INIT_RETRY_DELAY_SEC", 0)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        await risk_rules.init_risk_rules()

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert attempts == risk_rules._RISK_RULE_INIT_ATTEMPTS
    assert len(errors) == 1
    assert f"failed after {risk_rules._RISK_RULE_INIT_ATTEMPTS} attempts" in errors[0].getMessage()


@pytest.mark.asyncio
async def test_an_error_that_is_not_a_locked_database_is_not_retried(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    async def broken() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("bad rule table")

    monkeypatch.setattr(risk_rules, "_seed_and_load_risk_rules", broken)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        await risk_rules.init_risk_rules()

    assert attempts == 1
    assert "Risk rule initialization failed: bad rule table" in caplog.text
