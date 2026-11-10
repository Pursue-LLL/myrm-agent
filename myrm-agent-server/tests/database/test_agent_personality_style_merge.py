"""A custom agent that chose a communication style keeps it: the style text moves into its system prompt.

The tables below are the legacy layout the statements run against; they do not depend on the current ORM models.
After the merge the two ``personality_style`` columns are dropped.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.utils.db.migration_engine import MigrationStatement, StatefulMigrationEngine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database.migrations import MIGRATION_STATEMENTS
from app.database.personality_style_merge import (
    _BLOCK_PREFIX,
    _SCOPE,
    _STYLE_BODIES,
    MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL,
)

# The ledger stores the checksum of this exact text, so a database that already ran it depends on it staying as it is.
_STATEMENT_SHA256 = "e5ced6d567665d8936ba5cbc81871953c1cc609fb33fa4aac02736fb615413ff"
_LEDGER_POSITION = 247
_RETIREMENT_STATEMENTS = MIGRATION_STATEMENTS[_LEDGER_POSITION : _LEDGER_POSITION + 3]

_BODY_BY_STYLE = dict(_STYLE_BODIES)

# (id, system_prompt, personality_style, is_built_in)
_SEEDED: list[tuple[str, str | None, str, int]] = [
    ("friendly-with-prompt", "You help with taxes.", "friendly", 0),
    ("concise-null-prompt", None, "concise", 0),
    ("creative-empty-prompt", "", "creative", 0),
    ("default-style", "Keep it formal.", "professional", 0),
    ("unknown-style", "Plain prompt.", "mystery", 0),
    ("wrong-case-style", "Plain prompt.", "Friendly", 0),
    ("builtin-friendly", "Shipped prompt.", "friendly", 1),
    *[(f"style-{name}", "Base.", name, 0) for name, _ in _STYLE_BODIES],
]


def _block(style: str) -> str:
    return f"{_BLOCK_PREFIX}{_SCOPE} {_BODY_BY_STYLE[style]}"


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    db_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agents.db'}")
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE agents ("
                "id VARCHAR(255) PRIMARY KEY, name VARCHAR(255) NOT NULL DEFAULT '', system_prompt TEXT, "
                "personality_style VARCHAR(32) NOT NULL DEFAULT 'professional', "
                "is_built_in BOOLEAN NOT NULL DEFAULT 0)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE agent_profile_history (id VARCHAR(255) PRIMARY KEY, agent_id VARCHAR(255) NOT NULL "
                "REFERENCES agents (id) ON DELETE CASCADE, system_prompt TEXT, personality_style VARCHAR(32) NOT NULL)"
            )
        )
        await conn.execute(text("CREATE INDEX ix_agent_profile_history_agent_id ON agent_profile_history (agent_id)"))
        for agent_id, prompt, style, built_in in _SEEDED:
            await conn.execute(
                text("INSERT INTO agents (id, system_prompt, personality_style, is_built_in) VALUES (:i, :p, :s, :b)"),
                {"i": agent_id, "p": prompt, "s": style, "b": built_in},
            )
    yield db_engine
    await db_engine.dispose()


async def _prompts(engine: AsyncEngine) -> dict[str, str | None]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT id, system_prompt FROM agents"))
        return {agent_id: prompt for agent_id, prompt in rows}


async def _migrate(engine: AsyncEngine) -> None:
    report = await StatefulMigrationEngine(engine).run_migrations(
        [MigrationStatement(version=0, sql=MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL)]
    )
    assert report.failed_count == 0


async def _run_retirement(engine: AsyncEngine) -> int:
    """Run the merge and both column drops through the real ledger; return how many statements were applied."""
    report = await StatefulMigrationEngine(engine).run_migrations(
        [MigrationStatement(version=i, sql=sql) for i, sql in enumerate(_RETIREMENT_STATEMENTS)]
    )
    assert report.failed_count == 0
    return report.applied_count


async def _columns(engine: AsyncEngine, table: str) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text(f"PRAGMA table_info({table})"))}


def test_statement_text_is_frozen() -> None:
    assert hashlib.sha256(MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL.encode()).hexdigest() == _STATEMENT_SHA256


def test_statement_sits_at_its_ledger_position() -> None:
    assert MIGRATION_STATEMENTS.index(MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL) == _LEDGER_POSITION


@pytest.mark.asyncio
async def test_custom_agents_with_a_style_get_its_text_appended(engine: AsyncEngine) -> None:
    await _migrate(engine)
    prompts = await _prompts(engine)

    assert prompts["friendly-with-prompt"] == f"You help with taxes.\n\n{_block('friendly')}"


@pytest.mark.asyncio
async def test_an_agent_without_a_prompt_gets_the_text_alone(engine: AsyncEngine) -> None:
    await _migrate(engine)
    prompts = await _prompts(engine)

    assert prompts["concise-null-prompt"] == _block("concise")
    assert prompts["creative-empty-prompt"] == _block("creative")


@pytest.mark.asyncio
@pytest.mark.parametrize("style", [name for name, _ in _STYLE_BODIES])
async def test_every_non_default_style_is_merged_verbatim(engine: AsyncEngine, style: str) -> None:
    await _migrate(engine)

    assert (await _prompts(engine))[f"style-{style}"] == f"Base.\n\n{_block(style)}"


@pytest.mark.asyncio
async def test_default_unknown_and_built_in_rows_are_left_alone(engine: AsyncEngine) -> None:
    await _migrate(engine)
    prompts = await _prompts(engine)

    assert prompts["default-style"] == "Keep it formal."
    assert prompts["unknown-style"] == "Plain prompt."
    assert prompts["wrong-case-style"] == "Plain prompt."
    assert prompts["builtin-friendly"] == "Shipped prompt."


@pytest.mark.asyncio
async def test_the_ledger_applies_the_statement_only_once(engine: AsyncEngine) -> None:
    await _migrate(engine)
    first = await _prompts(engine)
    await _migrate(engine)

    assert await _prompts(engine) == first


def test_the_retirement_statements_are_the_merge_then_both_column_drops() -> None:
    assert _RETIREMENT_STATEMENTS == [
        MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL,
        "ALTER TABLE agents DROP COLUMN personality_style",
        "ALTER TABLE agent_profile_history DROP COLUMN personality_style",
    ]


@pytest.mark.asyncio
async def test_both_columns_are_dropped_and_the_merged_prompts_survive(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO agent_profile_history (id, agent_id, system_prompt, personality_style) VALUES ('h1', 'friendly-with-prompt', 'old', 'friendly')"
            )
        )

    assert await _run_retirement(engine) == 3

    assert "personality_style" not in await _columns(engine, "agents")
    assert "personality_style" not in await _columns(engine, "agent_profile_history")
    assert {"id", "system_prompt", "is_built_in"} <= await _columns(engine, "agents")
    assert (await _prompts(engine))["friendly-with-prompt"] == f"You help with taxes.\n\n{_block('friendly')}"
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT system_prompt FROM agent_profile_history WHERE id = 'h1'"))).scalar_one() == "old"


@pytest.mark.asyncio
async def test_running_the_retirement_again_changes_nothing(engine: AsyncEngine) -> None:
    await _run_retirement(engine)
    first = await _prompts(engine)

    assert await _run_retirement(engine) == 0
    assert await _prompts(engine) == first


@pytest.mark.asyncio
async def test_a_schema_without_the_columns_runs_the_retirement_without_failing(tmp_path: Path) -> None:
    """A database whose tables were created after the columns left the models has nothing to merge or drop."""
    db_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'current.db'}")
    async with db_engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE agents (id VARCHAR(255) PRIMARY KEY, system_prompt TEXT, is_built_in BOOLEAN NOT NULL DEFAULT 0)")
        )
        await conn.execute(text("CREATE TABLE agent_profile_history (id VARCHAR(255) PRIMARY KEY, system_prompt TEXT)"))
        await conn.execute(text("INSERT INTO agents (id, system_prompt) VALUES ('a', 'kept')"))

    await _run_retirement(db_engine)

    assert (await _prompts(db_engine)) == {"a": "kept"}
    await db_engine.dispose()
