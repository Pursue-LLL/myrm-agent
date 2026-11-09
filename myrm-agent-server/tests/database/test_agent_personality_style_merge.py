"""A custom agent that chose a communication style keeps it: the style text moves into its system prompt.

The table below is the legacy layout the statement runs against; it does not depend on the current ORM models.
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
