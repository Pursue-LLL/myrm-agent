"""The production engine keeps bound parameters out of the errors it raises, unless SQL echo is switched on.

SQLAlchemy writes ``[parameters: (...)]`` into ``str(error)``. Chat search binds what a person typed, so every WARNING
that prints a failed search would otherwise carry it into the logs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config.settings import settings
from app.database import factory
from app.database.operations.sqlite_storage_busy import is_sqlite_storage_busy

_TYPED_TEXT = "hunter2-typed-by-a-person"


@pytest.fixture
def scratch_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.database, "sqlite_path", str(tmp_path / "data.db"))
    monkeypatch.setattr(settings.database, "database_echo", False)


@pytest.mark.asyncio
@pytest.mark.usefixtures("scratch_database")
async def test_an_error_of_the_production_engine_does_not_carry_the_bound_parameters() -> None:
    engine = factory.create_engine()
    try:
        async with engine.connect() as conn:
            with pytest.raises(OperationalError) as caught:
                await conn.execute(text("INSERT INTO missing_table (content) VALUES (:content)"), {"content": _TYPED_TEXT})
    finally:
        await engine.dispose()

    assert "no such table" in str(caught.value)
    assert _TYPED_TEXT not in str(caught.value)
    assert _TYPED_TEXT in str(caught.value.params)


@pytest.mark.parametrize("echo", [False, True])
@pytest.mark.usefixtures("scratch_database")
def test_parameters_are_hidden_exactly_when_sql_echo_is_off(monkeypatch: pytest.MonkeyPatch, echo: bool) -> None:
    """Echo is the opt-in for seeing statements with their parameters, so it must not hide them."""
    monkeypatch.setattr(settings.database, "database_echo", echo)
    requested: dict[str, object] = {}

    def spy(url: str, **kwargs: object) -> AsyncEngine:
        requested.update(kwargs)
        # The real engine stays quiet: switching echo on would attach a stdout handler to the global SQLAlchemy logger.
        return create_async_engine(url, **{**kwargs, "echo": False})

    monkeypatch.setattr(factory, "create_async_engine", spy)

    factory.create_engine()

    assert requested["echo"] is echo
    assert requested["hide_parameters"] is (not echo)


def test_the_busy_check_still_sees_the_database_error_behind_hidden_parameters() -> None:
    error = OperationalError(
        "INSERT INTO messages (content) VALUES (?)",
        (_TYPED_TEXT,),
        sqlite3.OperationalError("database is locked"),
        hide_parameters=True,
    )

    assert is_sqlite_storage_busy(error)
    assert _TYPED_TEXT not in str(error)
