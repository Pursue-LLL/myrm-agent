"""Unit tests for cron SQLAlchemy mapping helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.cron.adapters.sqlalchemy_mapping import dict_to_monitor_config, normalize_monitor_config_payload
from app.core.cron.adapters.sqlalchemy_store import (
    SqlAlchemyCronStore,
    _normalize_job_monitor_config_in_place,
)


def test_dict_to_monitor_config_normalizes_hash_type() -> None:
    cfg = dict_to_monitor_config({"monitor_type": "HASH", "ttl_days": 14, "enabled": True})
    assert cfg is not None
    assert cfg.monitor_type == "hash"
    assert cfg.ttl_days == 14
    assert cfg.enabled is True


def test_dict_to_monitor_config_unknown_type_falls_back_to_set(caplog) -> None:
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
    row = SimpleNamespace(
        monitor_config={"monitor_type": "TIMESERIES", "ttl_days": "14", "enabled": 1, "extra": "unused"}
    )
    changed = _normalize_job_monitor_config_in_place(row)
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

    async def __aexit__(self, exc_type, exc, tb) -> bool:
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
    assert rows[0].monitor_config == {"monitor_type": "timeseries", "ttl_days": "7", "enabled": "1"}


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
    row = await store.get_job("job-2")

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
    normalized = await store.normalize_monitor_configs_batch(batch_size=10)

    assert normalized == 1
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
    normalized = await store.normalize_monitor_configs_batch(batch_size=5)

    assert normalized == 0
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_normalize_monitor_configs_batch_rejects_non_positive_batch_size() -> None:
    store = SqlAlchemyCronStore()
    with pytest.raises(ValueError, match="batch_size must be positive"):
        await store.normalize_monitor_configs_batch(batch_size=0)
