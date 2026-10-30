"""Unit tests for cron SQLAlchemy mapping helpers."""

import ast
import inspect
from collections.abc import AsyncIterator, Callable
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind

from app.core.cron.adapters import sqlalchemy_mapping
from app.core.cron.adapters.sqlalchemy_mapping import dict_to_monitor_config, normalize_monitor_config_payload
from app.core.cron.adapters.sqlalchemy_store import (
    SqlAlchemyCronStore,
    _normalize_job_monitor_config_in_place,
)
from app.database.models import CronJobModel
from tests.support.policy_sqlite import PolicyDb, policy_database


def test_dict_to_monitor_config_normalizes_hash_type() -> None:
    cfg = dict_to_monitor_config({"monitor_type": "HASH", "ttl_days": 14, "enabled": True})
    assert cfg is not None
    assert cfg.monitor_type == "hash"
    assert cfg.ttl_days == 14
    assert cfg.enabled is True


def test_dict_to_monitor_config_unknown_type_falls_back_to_set(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        cfg = dict_to_monitor_config({"monitor_type": "timeseries", "ttl_days": 30, "enabled": True})

    assert cfg is not None
    assert cfg.monitor_type == "set"
    assert "fallback to 'set'" in caplog.text


def test_normalize_monitor_config_payload_canonicalizes_legacy_shape() -> None:
    normalized, changed = normalize_monitor_config_payload(
        {
            "monitor_type": "timeseries",
            "ttl_days": "30",
            "enabled": 1,
            "legacy_extra": "x",
        }
    )
    assert changed is True
    assert normalized == {
        "monitor_type": "set",
        "ttl_days": 30,
        "enabled": True,
    }


def test_normalize_job_monitor_config_in_place_rewrites_row_payload() -> None:
    row = SimpleNamespace(monitor_config={"monitor_type": "TIMESERIES", "ttl_days": "14", "enabled": 1, "extra": "unused"})
    changed = _normalize_job_monitor_config_in_place(cast(CronJobModel, row))
    assert changed is True
    assert row.monitor_config == {
        "monitor_type": "set",
        "ttl_days": 14,
        "enabled": True,
    }


class _FakeExecResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeExecResult":
        return self

    def all(self) -> list[object]:
        return self._rows

    def scalar_one_or_none(self) -> object | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows: list[object] | None = None, result_batches: list[list[object]] | None = None) -> None:
        self._rows = rows or []
        self._result_batches = list(result_batches) if result_batches is not None else None
        self.commit = AsyncMock()

    async def execute(self, _stmt: object) -> _FakeExecResult:
        if self._result_batches is not None:
            if self._result_batches:
                return _FakeExecResult(self._result_batches.pop(0))
            return _FakeExecResult([])
        return _FakeExecResult(self._rows)


class _FakeSessionCtx:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_list_jobs_does_not_commit_when_monitor_config_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.cron.adapters import sqlalchemy_store as store_mod

    dirty_row = SimpleNamespace(
        id="job-1",
        monitor_config={"monitor_type": "timeseries", "ttl_days": "7", "enabled": "1"},
    )
    session = _FakeSession([dirty_row])
    monkeypatch.setattr(store_mod, "get_session", lambda: _FakeSessionCtx(session))
    monkeypatch.setattr(store_mod, "job_to_domain", lambda row: row)

    store = SqlAlchemyCronStore()
    rows = await store.list_jobs()

    session.commit.assert_not_awaited()
    assert cast(SimpleNamespace, rows[0]).monitor_config == {"monitor_type": "timeseries", "ttl_days": "7", "enabled": "1"}


@pytest.mark.asyncio
async def test_get_job_commits_when_monitor_config_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.cron.adapters import sqlalchemy_store as store_mod

    dirty_row = SimpleNamespace(
        id="job-2",
        monitor_config={"monitor_type": "timeseries", "ttl_days": "9", "enabled": 1, "extra": "drop"},
    )
    session = _FakeSession([dirty_row])
    monkeypatch.setattr(store_mod, "get_session", lambda: _FakeSessionCtx(session))
    monkeypatch.setattr(store_mod, "job_to_domain", lambda row: row)

    store = SqlAlchemyCronStore()
    row = cast(SimpleNamespace | None, await store.get_job("job-2"))
    assert row is not None

    session.commit.assert_awaited_once()
    assert row is dirty_row
    assert row.monitor_config == {"monitor_type": "set", "ttl_days": 9, "enabled": True}


@pytest.mark.asyncio
async def test_normalize_monitor_configs_batch_commits_only_changed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.cron.adapters import sqlalchemy_store as store_mod

    dirty_row = SimpleNamespace(
        id="job-a",
        monitor_config={"monitor_type": "timeseries", "ttl_days": "12", "enabled": 1},
    )
    clean_row = SimpleNamespace(
        id="job-b",
        monitor_config={"monitor_type": "set", "ttl_days": 3, "enabled": True},
    )
    session = _FakeSession(result_batches=[[dirty_row, clean_row], []])
    monkeypatch.setattr(store_mod, "get_session", lambda: _FakeSessionCtx(session))

    store = SqlAlchemyCronStore()
    stats = await store.normalize_monitor_configs_batch(batch_size=10)

    assert stats.normalized_count == 1
    assert stats.scanned_count == 2
    assert stats.processed_batches == 1
    assert stats.reached_batch_limit is False
    assert stats.continuation_required is False
    session.commit.assert_awaited_once()
    assert dirty_row.monitor_config == {"monitor_type": "set", "ttl_days": 12, "enabled": True}
    assert clean_row.monitor_config == {"monitor_type": "set", "ttl_days": 3, "enabled": True}


@pytest.mark.asyncio
async def test_normalize_monitor_configs_batch_no_changes_no_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.cron.adapters import sqlalchemy_store as store_mod

    clean_row = SimpleNamespace(
        id="job-c",
        monitor_config={"monitor_type": "hash", "ttl_days": 5, "enabled": True},
    )
    session = _FakeSession(result_batches=[[clean_row], []])
    monkeypatch.setattr(store_mod, "get_session", lambda: _FakeSessionCtx(session))

    store = SqlAlchemyCronStore()
    stats = await store.normalize_monitor_configs_batch(batch_size=5)

    assert stats.normalized_count == 0
    assert stats.scanned_count == 1
    assert stats.processed_batches == 1
    assert stats.reached_batch_limit is False
    assert stats.continuation_required is False
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_normalize_monitor_configs_batch_respects_max_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.cron.adapters import sqlalchemy_store as store_mod

    first_dirty = SimpleNamespace(
        id="job-d",
        monitor_config={"monitor_type": "timeseries", "ttl_days": "11", "enabled": 1},
    )
    second_dirty = SimpleNamespace(
        id="job-e",
        monitor_config={"monitor_type": "timeseries", "ttl_days": "15", "enabled": 1},
    )
    session = _FakeSession(result_batches=[[first_dirty], [second_dirty], []])
    monkeypatch.setattr(store_mod, "get_session", lambda: _FakeSessionCtx(session))

    store = SqlAlchemyCronStore()
    stats = await store.normalize_monitor_configs_batch(batch_size=1, max_batches=1)

    assert stats.normalized_count == 1
    assert stats.scanned_count == 1
    assert stats.processed_batches == 1
    assert stats.reached_batch_limit is True
    assert stats.continuation_required is True
    session.commit.assert_awaited_once()
    assert first_dirty.monitor_config == {"monitor_type": "set", "ttl_days": 11, "enabled": True}
    assert second_dirty.monitor_config == {"monitor_type": "timeseries", "ttl_days": "15", "enabled": 1}


@pytest.mark.asyncio
async def test_normalize_monitor_configs_batch_limit_without_remaining_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.cron.adapters import sqlalchemy_store as store_mod

    only_dirty = SimpleNamespace(
        id="job-f",
        monitor_config={"monitor_type": "timeseries", "ttl_days": "9", "enabled": 1},
    )
    session = _FakeSession(result_batches=[[only_dirty], []])
    monkeypatch.setattr(store_mod, "get_session", lambda: _FakeSessionCtx(session))

    store = SqlAlchemyCronStore()
    stats = await store.normalize_monitor_configs_batch(batch_size=1, max_batches=1)

    assert stats.normalized_count == 1
    assert stats.scanned_count == 1
    assert stats.processed_batches == 1
    assert stats.reached_batch_limit is True
    assert stats.continuation_required is False
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_normalize_monitor_configs_batch_rejects_non_positive_batch_size() -> None:
    store = SqlAlchemyCronStore()
    with pytest.raises(ValueError, match="batch_size must be positive"):
        await store.normalize_monitor_configs_batch(batch_size=0)
    with pytest.raises(ValueError, match="max_batches must be positive"):
        await store.normalize_monitor_configs_batch(max_batches=0)


_COLUMNS = frozenset(attr.key for attr in CronJobModel.__mapper__.column_attrs)
# The row id is the lookup key of an update; the database stamps ``created_at`` on insert and ``updated_at`` by default.
_NOT_COPIED_ON_UPDATE = frozenset({"id", "created_at"})
_NOT_COPIED_ON_CREATE = frozenset({"created_at", "updated_at"})


def _row_attributes(source: str, ctx: type[ast.expr_context]) -> set[str]:
    return {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ctx)
        and isinstance(node.value, ast.Name)
        and node.value.id == "m"
    }


def assigned_columns(source: str) -> set[str]:
    """Attributes assigned on the ORM row ``m``."""
    return _row_attributes(source, ast.Store)


def constructed_columns(source: str) -> set[str]:
    """Keyword arguments of every ``CronJobModel(...)`` call."""
    return {
        keyword.arg
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "CronJobModel"
        for keyword in node.keywords
        if keyword.arg
    }


def read_columns(source: str) -> set[str]:
    """Attributes read from the ORM row ``m``, directly or as ``getattr(m, "name", default)``."""
    named: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            row, name = node.args[:2]
            if isinstance(row, ast.Name) and row.id == "m" and isinstance(name, ast.Constant) and isinstance(name.value, str):
                named.add(name.value)
    return _row_attributes(source, ast.Load) | named


_MAPPING_PATHS = (
    pytest.param(sqlalchemy_mapping.apply_job_to_model, assigned_columns, _NOT_COPIED_ON_UPDATE, id="update"),
    pytest.param(sqlalchemy_mapping.job_to_model, constructed_columns, _NOT_COPIED_ON_CREATE, id="create"),
    pytest.param(sqlalchemy_mapping.job_to_domain, read_columns, frozenset[str](), id="read"),
)


@pytest.mark.parametrize(("mapper", "columns_used", "not_needed"), _MAPPING_PATHS)
def test_every_orm_column_is_mapped_on_each_path(
    mapper: Callable[..., object], columns_used: Callable[[str], set[str]], not_needed: frozenset[str]
) -> None:
    """A column the mapper never touches is accepted from the caller and then silently not stored (or not read back).

    Catches a dropped column, not a value taken from the wrong domain field.
    """
    unmapped = _COLUMNS - not_needed - columns_used(inspect.getsource(mapper))
    assert not unmapped, f"{mapper.__name__} never maps {sorted(unmapped)}"


# ``user_id`` is read back as the single user "default"; no code reads the other three, and the only write is
# ``duplicate_job`` resetting ``job_scratchpad`` to empty.
_NOT_PERSISTED_FIELDS = frozenset({"user_id", "continuity", "job_scratchpad", "target_bot_agent_id"})


def test_every_cron_job_field_has_a_column_or_is_listed_as_not_persisted() -> None:
    """A field without a column is accepted by every layer above the store and is lost when the job is read back."""
    without_column = {field.name for field in fields(CronJob)} - _COLUMNS
    assert without_column == _NOT_PERSISTED_FIELDS, sorted(without_column ^ _NOT_PERSISTED_FIELDS)


@pytest.mark.parametrize(
    ("mapper", "columns_used", "mapping"),
    [
        pytest.param(
            sqlalchemy_mapping.apply_job_to_model, assigned_columns, "m.skip_if_active = job.skip_if_active", id="update"
        ),
        pytest.param(sqlalchemy_mapping.job_to_model, constructed_columns, "skip_if_active=job.skip_if_active,", id="create"),
        pytest.param(
            sqlalchemy_mapping.job_to_domain,
            read_columns,
            'skip_if_active=getattr(m, "skip_if_active", False) or False,',
            id="read",
        ),
    ],
)
def test_column_detectors_notice_a_removed_mapping(
    mapper: Callable[..., object], columns_used: Callable[[str], set[str]], mapping: str
) -> None:
    """Without this, an always-empty detector would keep the coverage guard green."""
    source = inspect.getsource(mapper)
    assert mapping in source
    assert "skip_if_active" in columns_used(source)
    assert "skip_if_active" not in columns_used(source.replace(mapping, "pass" if mapping.startswith("m.") else ""))


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "cron.db", monkeypatch) as db:
        yield db


def _job(pre_condition_script: str | None = None) -> CronJob:
    return CronJob(
        id="mapped",
        user_id="user",
        name="mapped",
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0),
        command="__probe__",
        pre_condition_script=pre_condition_script,
    )


@pytest.mark.asyncio
async def test_save_job_stores_an_edited_and_a_cleared_option_on_the_existing_row(policy_db: PolicyDb) -> None:
    """An edit rewrites the stored row through its own mapper, so only a read-back from the database shows an option
    that is stored at creation but not when the job is edited."""
    store = SqlAlchemyCronStore()
    created = await store.save_job(_job(pre_condition_script="test -f /tmp/a"))

    await store.save_job(replace(created, pre_condition_script="test -f /tmp/b", skip_if_active=True))
    edited = await store.get_job(created.id)
    assert edited is not None
    assert (edited.pre_condition_script, edited.skip_if_active) == ("test -f /tmp/b", True)

    await store.save_job(replace(edited, pre_condition_script=None, skip_if_active=False))
    cleared = await store.get_job(created.id)
    assert cleared is not None
    assert (cleared.pre_condition_script, cleared.skip_if_active) == (None, False)
