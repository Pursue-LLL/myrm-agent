"""Unit tests for BSDL Core BackgroundJobStore."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background import job_store as job_store_module
from myrm_agent_harness.agent.meta_tools.bash._background.job_store import (
    BackgroundJobStore,
    configure_background_job_store,
    get_background_job_store,
    reset_background_job_store_for_tests,
)
from myrm_agent_harness.agent.meta_tools.bash._background.job_store_core import (
    BackgroundJobRecord,
    BackgroundJobStoreStatus,
    map_store_status_to_shell_task_status,
    reconcile_orphaned_job_ids,
)
from myrm_agent_harness.agent.meta_tools.bash._background.termination import GroupMember, LedgerLeader

_JOB_STORE = "myrm_agent_harness.agent.meta_tools.bash._background.job_store"
_STORAGE_ROOT = (
    "myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind.workspace_storage_fs_root_strict"
)


@pytest.fixture(autouse=True)
def _isolated_singleton() -> Iterator[None]:
    reset_background_job_store_for_tests()
    yield
    reset_background_job_store_for_tests()


@pytest.fixture
def store(tmp_path: Path) -> BackgroundJobStore:
    return BackgroundJobStore(tmp_path / "bg_jobs.db")


def _insert(
    store: BackgroundJobStore,
    job_id: str,
    *,
    pid: int = 100,
    session_id: str = "chat-1",
    owner: GroupMember | None = None,
) -> None:
    store.insert_running(job_id=job_id, pid=pid, session_id=session_id, command="cmd", started_at=1.0, owner=owner)


def test_insert_and_get_running(store: BackgroundJobStore) -> None:
    store.insert_running(
        job_id="job-a",
        pid=100,
        session_id="chat-1",
        command="npm test",
        started_at=1.0,
    )
    record = store.get_by_job_id("job-a")
    assert record is not None
    assert record.status == "running"
    assert record.pid == 100
    assert record.owner_pid is None
    assert record.owner_start_stamp is None


def test_the_registering_server_is_recorded_with_the_job(store: BackgroundJobStore) -> None:
    _insert(store, "job-owned", owner=GroupMember(pid=777, start_stamp=5.5))

    record = store.get_by_job_id("job-owned")

    assert record is not None
    assert (record.owner_pid, record.owner_start_stamp) == (777, 5.5)


def test_new_job_ids_are_unique() -> None:
    assert BackgroundJobStore.new_job_id() != BackgroundJobStore.new_job_id()


def test_a_job_id_is_recorded_once(store: BackgroundJobStore) -> None:
    _insert(store, "job-dup", pid=1)

    with pytest.raises(sqlite3.IntegrityError):
        _insert(store, "job-dup", pid=2)

    assert [record.pid for record in store.list_recent()] == [1]


def test_finish_dedupe_claim(store: BackgroundJobStore) -> None:
    store.insert_running(
        job_id="job-f",
        pid=101,
        session_id="chat-1",
        command="echo",
        started_at=1.0,
    )
    store.update_terminal(
        "job-f",
        status="exited",
        exit_code=0,
        error_category=None,
        completed_at=2.0,
    )
    assert store.try_claim_finish("job-f") is True
    assert store.try_claim_finish("job-f") is False


def test_finish_is_claimed_once_by_session_and_pid_for_rows_without_a_known_job_id(store: BackgroundJobStore) -> None:
    _insert(store, "job-legacy", pid=55, session_id="chat-9")
    store.update_terminal("job-legacy", status="exited", exit_code=0, error_category=None, completed_at=2.0)

    assert store.try_claim_finish_by_session_pid("chat-9", 55) is True
    assert store.try_claim_finish_by_session_pid("chat-9", 55) is False
    assert store.try_claim_finish_by_session_pid("chat-other", 55) is False


def test_a_terminal_update_keeps_the_log_reference_it_is_given(store: BackgroundJobStore) -> None:
    _insert(store, "job-log")

    store.update_terminal(
        "job-log",
        status="killed",
        exit_code=137,
        error_category="killed",
        completed_at=3.0,
        vault_log_ref="vault://log-1",
    )

    record = store.get_by_job_id("job-log")
    assert record is not None
    assert (record.status, record.exit_code, record.vault_log_ref) == ("killed", 137, "vault://log-1")


def test_the_log_reference_can_be_attached_after_the_job_ended(store: BackgroundJobStore) -> None:
    _insert(store, "job-late-log")

    store.set_vault_log_ref("job-late-log", "vault://late")

    record = store.get_by_job_id("job-late-log")
    assert record is not None
    assert record.vault_log_ref == "vault://late"


def test_lookup_by_pid_returns_the_newest_job_of_a_reused_pid(store: BackgroundJobStore) -> None:
    store.insert_running(job_id="job-old", pid=9, session_id="s", command="a", started_at=1.0)
    store.insert_running(job_id="job-new", pid=9, session_id="s", command="b", started_at=2.0)

    newest = store.get_by_pid(9)

    assert newest is not None
    assert newest.job_id == "job-new"
    assert store.get_by_pid(10) is None
    assert store.get_by_job_id("job-missing") is None


def test_recent_jobs_can_be_listed_for_one_session(store: BackgroundJobStore) -> None:
    _insert(store, "job-1", session_id="chat-a")
    _insert(store, "job-2", session_id="chat-b")

    assert [record.job_id for record in store.list_recent(session_id="chat-a")] == ["job-1"]
    assert {record.job_id for record in store.list_recent()} == {"job-1", "job-2"}


def test_a_status_the_store_does_not_know_reads_as_exited(store: BackgroundJobStore) -> None:
    _insert(store, "job-odd")
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute("UPDATE background_jobs SET status = 'paused' WHERE job_id = 'job-odd'")

    record = store.get_by_job_id("job-odd")

    assert record is not None
    assert record.status == "exited"


def test_reconcile_orphans_running_without_live_pid(store: BackgroundJobStore) -> None:
    store.insert_running(
        job_id="job-o",
        pid=202,
        session_id="chat-2",
        command="sleep",
        started_at=1.0,
    )
    count = store.reconcile_running_jobs(frozenset())
    assert count == 1
    record = store.get_by_job_id("job-o")
    assert record is not None
    assert record.status == "orphaned"


def test_reconcile_stops_the_surviving_group_of_each_orphaned_job_only(store: BackgroundJobStore) -> None:
    store.insert_running(
        job_id="job-gone",
        pid=4242,
        session_id="chat-3",
        command="serve",
        started_at=100.0,
        owner=GroupMember(pid=900, start_stamp=50.0),
    )
    store.insert_running(job_id="job-live", pid=4243, session_id="chat-3", command="serve", started_at=101.0)

    with patch(f"{_JOB_STORE}.reap_orphaned_groups", return_value=1) as reap:
        count = store.reconcile_running_jobs(frozenset({4243}))

    assert count == 1
    assert list(reap.call_args.args[0]) == [LedgerLeader(4242, 100.0, GroupMember(pid=900, start_stamp=50.0))]
    live = store.get_by_job_id("job-live")
    assert live is not None
    assert live.status == "running"


def test_reconcile_hands_over_a_job_recorded_without_its_server_as_unrecorded(store: BackgroundJobStore) -> None:
    store.insert_running(job_id="job-bare", pid=4244, session_id="chat-3", command="serve", started_at=100.0)

    with patch(f"{_JOB_STORE}.reap_orphaned_groups", return_value=0) as reap:
        store.reconcile_running_jobs(frozenset())

    assert list(reap.call_args.args[0]) == [LedgerLeader(4244, 100.0, None)]


def test_a_row_with_half_a_server_record_counts_as_unrecorded(store: BackgroundJobStore) -> None:
    _insert(store, "job-half", pid=4245, owner=GroupMember(pid=900, start_stamp=50.0))
    with closing(sqlite3.connect(store.db_path)) as conn, conn:
        conn.execute("UPDATE background_jobs SET owner_start_stamp = NULL WHERE job_id = 'job-half'")

    with patch(f"{_JOB_STORE}.reap_orphaned_groups", return_value=0) as reap:
        store.reconcile_running_jobs(frozenset())

    assert list(reap.call_args.args[0]) == [LedgerLeader(4245, 1.0, None)]


def _record_of(job_id: str, *, pid: int | None, status: BackgroundJobStoreStatus = "running") -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=job_id,
        pid=pid,
        session_id="s",
        command="c",
        status=status,
        started_at=0.0,
        completed_at=None,
        exit_code=None,
        error_category=None,
        finish_processed=False,
        vault_log_ref=None,
    )


def test_reconcile_core_helper() -> None:
    orphaned = reconcile_orphaned_job_ids(
        frozenset({"j1"}),
        frozenset(),
        records_by_job_id={"j1": _record_of("j1", pid=1)},
    )
    assert orphaned == ("j1",)


def test_only_a_running_job_without_a_live_pid_is_orphaned() -> None:
    records = {
        "alive": _record_of("alive", pid=10),
        "no-pid": _record_of("no-pid", pid=None),
        "done": _record_of("done", pid=11, status="exited"),
    }

    orphaned = reconcile_orphaned_job_ids(
        frozenset({"alive", "no-pid", "done", "unknown"}), frozenset({10}), records_by_job_id=records
    )

    assert orphaned == ("no-pid",)


@pytest.mark.parametrize(
    ("status", "exit_code", "expected"),
    [
        ("running", None, "running"),
        ("orphaned", None, "orphaned"),
        ("killed", None, "cancelled"),
        ("exited", 0, "completed"),
        ("exited", None, "completed"),
        ("exited", 3, "failed"),
    ],
)
def test_store_status_maps_to_the_panel_status(
    status: BackgroundJobStoreStatus, exit_code: int | None, expected: str
) -> None:
    assert map_store_status_to_shell_task_status(status, exit_code) == expected


def test_configuring_the_same_path_again_returns_the_same_store(tmp_path: Path) -> None:
    first = configure_background_job_store(tmp_path / "a.db")

    assert configure_background_job_store(tmp_path / "a.db") is first
    assert configure_background_job_store(tmp_path / "b.db") is not first
    assert get_background_job_store() is not first


def test_the_store_is_rebuilt_from_the_configured_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_store_module, "_CONFIGURED_PATH", tmp_path / "configured.db")

    store = get_background_job_store()

    assert store is not None
    assert store.db_path == tmp_path / "configured.db"
    assert get_background_job_store() is store


def test_the_store_is_bound_to_the_workspace_storage_root(tmp_path: Path) -> None:
    with patch(_STORAGE_ROOT, return_value=tmp_path):
        store = get_background_job_store()

    assert store is not None
    assert store.db_path == (tmp_path / ".myrm" / "background_jobs.db").resolve()


def test_there_is_no_store_without_a_workspace_storage_root() -> None:
    with patch(_STORAGE_ROOT, side_effect=RuntimeError("not bound")):
        assert get_background_job_store() is None
