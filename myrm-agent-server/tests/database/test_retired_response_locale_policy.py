"""The migration removes the ``response_locale_policy`` key from saved agents and rollback snapshots.

It touches only rows that hold the key, keeps every other parameter, leaves rows that are not valid JSON alone, and
does not rewrite the read-only edit history.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database import migrations
from app.database.migrations import (
    MIGRATION_STATEMENTS,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL,
)
from app.database.models import Agent
from app.database.models.agent import AgentProfileSnapshot
from app.database.models.agent_history import AgentProfileHistory
from app.database.models.base import Base

_POLICY = {"locale": "ko-KR", "formality": "formal-polite"}
_HISTORY_DATA = {"engine_params": {"response_locale_policy": _POLICY}}

# agent id -> ``engine_params`` as stored (None is SQL NULL), including forms no valid save writes.
_AGENT_PARAMS: dict[str, str | None] = {
    "only-policy": json.dumps({"response_locale_policy": _POLICY}),
    "policy-with-others": json.dumps({"max_parallel": 3, "response_locale_policy": _POLICY, "moa_overlay": {"mode": "x"}}),
    "policy-null-value": '{"response_locale_policy": null, "keep": 1}',
    "no-policy": json.dumps({"max_parallel": 2}),
    "empty-object": "{}",
    "json-null": "null",
    "sql-null": None,
    "array-root": "[1, 2]",
    "malformed": "{not json",
}
# The rows the statement rewrites; None is SQL NULL, the form a save writes for an agent with no parameters.
_AGENT_CHANGED: dict[str, object] = {
    "only-policy": None,
    "policy-with-others": {"max_parallel": 3, "moa_overlay": {"mode": "x"}},
    "policy-null-value": {"keep": 1},
}

_SNAPSHOT_DATA: dict[str, str] = {
    "snap-with-others": json.dumps(
        {"display_name": "A", "engine_params": {"max_parallel": 2, "response_locale_policy": _POLICY}}
    ),
    "snap-only-policy": json.dumps({"engine_params": {"response_locale_policy": _POLICY}}),
    "snap-null-params": json.dumps({"engine_params": None}),
    "snap-no-params": json.dumps({"display_name": "B"}),
    "snap-malformed": "{not json",
}
_SNAPSHOT_CHANGED: dict[str, object] = {
    "snap-with-others": {"display_name": "A", "engine_params": {"max_parallel": 2}},
    "snap-only-policy": {"engine_params": {}},
}

_HOLDER_ID = "snapshot-holder"


def _agent(agent_id: str) -> Agent:
    return Agent(
        id=agent_id,
        name=agent_id,
        description="",
        skill_ids=[],
        mcp_servers=[],
        subagent_ids=[],
        model_config={},
    )


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agents.db'}")
    tables = [Base.metadata.tables[name] for name in ("agents", "agent_profile_snapshots", "agent_profile_history")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add_all(_agent(agent_id) for agent_id in (*_AGENT_PARAMS, _HOLDER_ID))
        await db.flush()
        db.add_all(AgentProfileSnapshot(id=snapshot_id, agent_id=_HOLDER_ID, snapshot_data={}) for snapshot_id in _SNAPSHOT_DATA)
        db.add(AgentProfileHistory(id="history-1", agent_id=_HOLDER_ID, version=1, name="v1", snapshot_data=_HISTORY_DATA))
        await db.flush()
        # Raw writes store the exact text, including values the ORM would never produce.
        for agent_id, raw in _AGENT_PARAMS.items():
            await db.execute(text("UPDATE agents SET engine_params = :raw WHERE id = :id"), {"raw": raw, "id": agent_id})
        for snapshot_id, raw in _SNAPSHOT_DATA.items():
            await db.execute(
                text("UPDATE agent_profile_snapshots SET snapshot_data = :raw WHERE id = :id"),
                {"raw": raw, "id": snapshot_id},
            )
        await db.commit()
    yield factory
    await engine.dispose()


async def _run(factory: async_sessionmaker[AsyncSession], statement: str) -> int:
    async with factory() as db:
        result = await db.execute(text(statement))
        await db.commit()
        return result.rowcount


async def _stored(factory: async_sessionmaker[AsyncSession], sql: str) -> dict[str, str | None]:
    async with factory() as db:
        return {row[0]: row[1] for row in (await db.execute(text(sql))).all()}


async def _agent_params(factory: async_sessionmaker[AsyncSession]) -> dict[str, str | None]:
    return await _stored(factory, "SELECT id, engine_params FROM agents")


async def _snapshots(factory: async_sessionmaker[AsyncSession]) -> dict[str, str | None]:
    return await _stored(factory, "SELECT id, snapshot_data FROM agent_profile_snapshots")


_FIRST = MIGRATION_STATEMENTS.index(STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL)


def test_both_statements_are_registered_once_and_in_order() -> None:
    assert MIGRATION_STATEMENTS.count(STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL) == 1
    assert MIGRATION_STATEMENTS.count(STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL) == 1
    assert MIGRATION_STATEMENTS[_FIRST : _FIRST + 2] == [
        STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL,
        STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL,
    ]


@pytest.mark.asyncio
async def test_agents_lose_only_the_retired_key(session_factory: async_sessionmaker[AsyncSession]) -> None:
    changed = await _run(session_factory, STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL)

    after = await _agent_params(session_factory)
    assert changed == len(_AGENT_CHANGED)
    for agent_id, raw in _AGENT_PARAMS.items():
        if agent_id not in _AGENT_CHANGED:
            assert after[agent_id] == raw, agent_id
        elif _AGENT_CHANGED[agent_id] is None:
            assert after[agent_id] is None, agent_id
        else:
            stored = after[agent_id]
            assert stored is not None
            assert json.loads(stored) == _AGENT_CHANGED[agent_id], agent_id


@pytest.mark.asyncio
async def test_snapshots_lose_only_the_retired_key(session_factory: async_sessionmaker[AsyncSession]) -> None:
    changed = await _run(session_factory, STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL)

    after = await _snapshots(session_factory)
    assert changed == len(_SNAPSHOT_CHANGED)
    for snapshot_id, raw in _SNAPSHOT_DATA.items():
        if snapshot_id not in _SNAPSHOT_CHANGED:
            assert after[snapshot_id] == raw, snapshot_id
        else:
            stored = after[snapshot_id]
            assert stored is not None
            assert json.loads(stored) == _SNAPSHOT_CHANGED[snapshot_id], snapshot_id


@pytest.mark.asyncio
async def test_the_edit_history_keeps_what_each_version_held(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _run(session_factory, STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL)
    await _run(session_factory, STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL)

    history = await _stored(session_factory, "SELECT id, snapshot_data FROM agent_profile_history")
    stored = history["history-1"]
    assert stored is not None
    assert json.loads(stored) == _HISTORY_DATA


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statement",
    [STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL, STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL],
)
async def test_running_a_statement_again_changes_nothing(
    session_factory: async_sessionmaker[AsyncSession], statement: str
) -> None:
    await _run(session_factory, statement)
    agents, snapshots = await _agent_params(session_factory), await _snapshots(session_factory)

    assert await _run(session_factory, statement) == 0
    assert (await _agent_params(session_factory), await _snapshots(session_factory)) == (agents, snapshots)


@pytest.mark.asyncio
async def test_the_migration_ledger_applies_both_statements_when_a_database_upgrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine: AsyncEngine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrade.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", MIGRATION_STATEMENTS[:_FIRST])
    await migrations.run_migrations(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(_agent("saved"))
        await db.flush()
        db.add(AgentProfileSnapshot(id="snap", agent_id="saved", snapshot_data={"engine_params": {"keep": 1}}))
        await db.flush()
        await db.execute(text("UPDATE agents SET engine_params = :raw"), {"raw": _AGENT_PARAMS["policy-with-others"]})
        await db.execute(
            text("UPDATE agent_profile_snapshots SET snapshot_data = :raw"), {"raw": _SNAPSHOT_DATA["snap-with-others"]}
        )
        await db.commit()

    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", MIGRATION_STATEMENTS[: _FIRST + 2])
    assert await migrations.has_pending_migrations(engine)
    await migrations.run_migrations(engine)

    assert not await migrations.has_pending_migrations(engine)
    agents = await _agent_params(factory)
    snapshots = await _snapshots(factory)
    assert json.loads(agents["saved"] or "null") == _AGENT_CHANGED["policy-with-others"]
    assert json.loads(snapshots["snap"] or "null") == _SNAPSHOT_CHANGED["snap-with-others"]
    await engine.dispose()
