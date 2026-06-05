"""Tests for repair/actions.py.

Covers:
- build_repair_actions from various health report combinations
- execute_repair_action for non-executable, executable, dry_run, confirm flows
- Deduplication logic
- Empty inputs
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

import app.services.repair.actions as _actions_module
from app.services.repair.actions import (
    RepairActionExecuteRequest,
    RepairActionId,
    build_repair_actions,
    execute_repair_action,
)

_original_sqlite_backup_action = _actions_module._sqlite_backup_action


@pytest.fixture(autouse=True)
def _suppress_sqlite_backup_action():
    """Prevent _sqlite_backup_action from detecting test-environment SQLite files."""
    with patch("app.services.repair.actions._sqlite_backup_action", return_value=None):
        yield


def _report(name: str, status: str, message: str = "test", detail: str | None = None) -> HealthReport:
    return HealthReport(component_name=name, status=status, message=message, detail=detail)


@pytest.mark.asyncio
async def test_build_empty_reports_returns_empty() -> None:
    actions = await build_repair_actions([], [])
    assert actions == []


@pytest.mark.asyncio
async def test_build_pass_reports_returns_empty() -> None:
    reports = [_report("Network", "pass"), _report("Database", "pass")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 0


@pytest.mark.asyncio
async def test_build_workspace_storage_fail() -> None:
    reports = [_report("WorkspaceStorage", "fail", "Disk full")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    action = actions[0]
    assert action.action_id == RepairActionId.REVIEW_WORKSPACE_STORAGE
    assert action.executable is False
    assert action.reason == "Disk full"


@pytest.mark.asyncio
async def test_build_database_warn() -> None:
    reports = [_report("Database", "warn", "WAL large")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_WORKSPACE_STORAGE


@pytest.mark.asyncio
async def test_build_network_fail() -> None:
    reports = [_report("Network", "fail", "DNS resolution failed")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_RUNTIME_DEPENDENCY
    assert actions[0].component == "Network"


@pytest.mark.asyncio
async def test_build_vectordb_warn() -> None:
    reports = [_report("VectorDB", "warn", "Qdrant slow")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_RUNTIME_DEPENDENCY


@pytest.mark.asyncio
async def test_build_dlq_fail_from_server_reports() -> None:
    server_reports: list[dict[str, object]] = [{"component_name": "DLQ", "status": "fail", "message": "500 failed msgs"}]
    actions = await build_repair_actions([], server_reports)
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_CHANNEL_DLQ


@pytest.mark.asyncio
async def test_build_dlq_pass_ignored() -> None:
    server_reports: list[dict[str, object]] = [{"component_name": "DLQ", "status": "pass", "message": "0 failed"}]
    actions = await build_repair_actions([], server_reports)
    dlq_actions = [a for a in actions if a.action_id == RepairActionId.REVIEW_CHANNEL_DLQ]
    assert len(dlq_actions) == 0


@pytest.mark.asyncio
async def test_build_deduplication() -> None:
    reports = [
        _report("WorkspaceStorage", "fail", "Disk full"),
        _report("WorkspaceStorage", "warn", "Also warn"),
    ]
    actions = await build_repair_actions(reports, [])
    ws_actions = [a for a in actions if a.action_id == RepairActionId.REVIEW_WORKSPACE_STORAGE]
    assert len(ws_actions) == 1


@pytest.mark.asyncio
async def test_build_unknown_component_ignored() -> None:
    reports = [_report("SomethingNew", "fail", "Unknown")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 0


@pytest.mark.asyncio
async def test_execute_non_executable_action() -> None:
    result = await execute_repair_action(
        RepairActionId.REVIEW_WORKSPACE_STORAGE,
        RepairActionExecuteRequest(dry_run=False, confirm=True),
    )
    assert result.status == "not_executable"
    assert result.changed is False


@pytest.mark.asyncio
async def test_execute_review_dlq_not_executable() -> None:
    result = await execute_repair_action(
        RepairActionId.REVIEW_CHANNEL_DLQ,
        RepairActionExecuteRequest(dry_run=True, confirm=False),
    )
    assert result.status == "not_executable"


@pytest.mark.asyncio
async def test_execute_review_runtime_dependency_not_executable() -> None:
    result = await execute_repair_action(
        RepairActionId.REVIEW_RUNTIME_DEPENDENCY,
        RepairActionExecuteRequest(dry_run=False, confirm=True),
    )
    assert result.status == "not_executable"


# ---------- SystemResources / AgentEngine fail/warn ----------


@pytest.mark.asyncio
async def test_build_system_resources_warn() -> None:
    reports = [_report("SystemResources", "warn", "Memory usage 92%")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_RUNTIME_DEPENDENCY
    assert actions[0].component == "SystemResources"


@pytest.mark.asyncio
async def test_build_agent_engine_fail() -> None:
    reports = [_report("AgentEngine", "fail", "Terminal error")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_RUNTIME_DEPENDENCY
    assert actions[0].component == "AgentEngine"


# ---------- DLQ warn also triggers action ----------


@pytest.mark.asyncio
async def test_build_dlq_warn_triggers_action() -> None:
    server_reports: list[dict[str, object]] = [{"component_name": "DLQ", "status": "warn", "message": "DLQ growing"}]
    actions = await build_repair_actions([], server_reports)
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_CHANNEL_DLQ


# ---------- Combined harness + server reports ----------


@pytest.mark.asyncio
async def test_build_combined_harness_and_server() -> None:
    harness = [
        _report("Network", "fail", "DNS fail"),
        _report("Database", "warn", "WAL large"),
    ]
    server: list[dict[str, object]] = [{"component_name": "DLQ", "status": "fail", "message": "500 failed"}]
    actions = await build_repair_actions(harness, server)
    action_ids = {a.action_id for a in actions}
    assert RepairActionId.REVIEW_RUNTIME_DEPENDENCY in action_ids
    assert RepairActionId.REVIEW_WORKSPACE_STORAGE in action_ids
    assert RepairActionId.REVIEW_CHANNEL_DLQ in action_ids
    assert len(actions) == 3


# ---------- Browser orphan action ----------


@pytest.mark.asyncio
async def test_browser_orphan_action_no_orphans_returns_none() -> None:
    """When no orphan processes exist, _browser_orphan_action skips."""
    from unittest.mock import patch

    import app.services.repair.actions as actions_mod

    async def _no_orphans() -> None:
        return None

    with patch.object(actions_mod, "_browser_orphan_action", _no_orphans):
        actions = await build_repair_actions([], [])
    assert all(a.action_id != RepairActionId.CLEANUP_BROWSER_ORPHANS for a in actions)


@pytest.mark.asyncio
async def test_browser_orphan_import_failure() -> None:
    """When browser toolkit is not installed, _browser_orphan_action returns None."""
    from unittest.mock import patch

    import app.services.repair.actions as actions_mod

    async def _import_fails() -> None:
        return None

    with patch.object(actions_mod, "_browser_orphan_action", _import_fails):
        actions = await build_repair_actions([], [])
    assert all(a.action_id != RepairActionId.CLEANUP_BROWSER_ORPHANS for a in actions)


# ---------- execute_repair_action for CLEANUP_BROWSER_ORPHANS ----------


@pytest.mark.asyncio
async def test_execute_cleanup_browser_no_orphans() -> None:
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[]):
        result = await execute_repair_action(
            RepairActionId.CLEANUP_BROWSER_ORPHANS,
            RepairActionExecuteRequest(dry_run=False, confirm=True),
        )
    assert result.status == "skipped"
    assert result.changed is False


@pytest.mark.asyncio
async def test_execute_cleanup_browser_dry_run() -> None:
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[{"pid": 111}]):
        with patch(
            "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
            return_value={"killed": 0, "message": "dry run", "dry_run": True, "failed": []},
        ) as mock_cleanup:
            result = await execute_repair_action(
                RepairActionId.CLEANUP_BROWSER_ORPHANS,
                RepairActionExecuteRequest(dry_run=True, confirm=False),
            )
    assert result.status == "dry_run"
    assert result.dry_run is True
    mock_cleanup.assert_called_once_with([111], force=False)


@pytest.mark.asyncio
async def test_execute_cleanup_browser_needs_confirm() -> None:
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[{"pid": 222}]):
        result = await execute_repair_action(
            RepairActionId.CLEANUP_BROWSER_ORPHANS,
            RepairActionExecuteRequest(dry_run=False, confirm=False),
        )
    assert result.status == "confirmation_required"
    assert result.changed is False
    assert 222 in result.details["orphan_pids"]


@pytest.mark.asyncio
async def test_execute_cleanup_browser_confirmed() -> None:
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[{"pid": 333}]):
        with patch(
            "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
            return_value={"killed": 1, "message": "killed 1", "failed": []},
        ) as mock_cleanup:
            result = await execute_repair_action(
                RepairActionId.CLEANUP_BROWSER_ORPHANS,
                RepairActionExecuteRequest(dry_run=False, confirm=True),
            )
    assert result.status == "completed"
    assert result.changed is True
    assert result.details["killed"] == 1
    mock_cleanup.assert_called_once_with([333], force=True)


# ---------- RepairAction model fields ----------


@pytest.mark.asyncio
async def test_repair_action_fields_completeness() -> None:
    reports = [_report("Network", "fail", "Timeout")]
    actions = await build_repair_actions(reports, [])
    action = actions[0]
    assert action.title
    assert action.description
    assert action.component == "Network"
    assert action.layer == "harness"
    assert action.scope == "current_runtime"
    assert action.risk_level in {"low", "medium", "high"}
    assert action.requires_approval is True
    assert isinstance(action.does_not_do, list)
    assert len(action.does_not_do) > 0
    assert action.expected_effect
    assert action.reason == "Timeout"


# ---------- execute edge cases ----------


@pytest.mark.asyncio
async def test_execute_cleanup_browser_orphan_missing_pid_key() -> None:
    """Orphans without a 'pid' key are filtered out by the list comprehension."""
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[{"name": "chrome"}]):
        result = await execute_repair_action(
            RepairActionId.CLEANUP_BROWSER_ORPHANS,
            RepairActionExecuteRequest(dry_run=False, confirm=True),
        )
    assert result.status == "skipped"
    assert result.changed is False


@pytest.mark.asyncio
async def test_execute_cleanup_browser_confirmed_killed_zero() -> None:
    """When cleanup runs but kills 0 processes, changed should be False."""
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[{"pid": 444}]):
        with patch(
            "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
            return_value={"killed": 0, "message": "process already dead", "failed": [444]},
        ):
            result = await execute_repair_action(
                RepairActionId.CLEANUP_BROWSER_ORPHANS,
                RepairActionExecuteRequest(dry_run=False, confirm=True),
            )
    assert result.status == "completed"
    assert result.changed is False
    assert result.details["killed"] == 0
    assert 444 in result.details["failed"]


# ---------- RepairActionExecuteRequest default values ----------


@pytest.mark.asyncio
async def test_execute_request_default_values() -> None:
    """RepairActionExecuteRequest defaults: dry_run=True, confirm=False."""
    req = RepairActionExecuteRequest()
    assert req.dry_run is True
    assert req.confirm is False


# ---------- Deduplication with different components same action_id ----------


@pytest.mark.asyncio
async def test_dedup_different_components_same_action_id() -> None:
    """Network + VectorDB both map to REVIEW_RUNTIME_DEPENDENCY but have different components, so both kept."""
    reports = [
        _report("Network", "fail", "DNS fail"),
        _report("VectorDB", "warn", "Qdrant slow"),
    ]
    actions = await build_repair_actions(reports, [])
    runtime_actions = [a for a in actions if a.action_id == RepairActionId.REVIEW_RUNTIME_DEPENDENCY]
    components = {a.component for a in runtime_actions}
    assert "Network" in components
    assert "VectorDB" in components
    assert len(runtime_actions) == 2


# ---------- Browser orphan action in build_repair_actions ----------


@pytest.mark.asyncio
async def test_build_includes_browser_orphan_action_when_orphans_exist() -> None:
    """build_repair_actions includes CLEANUP_BROWSER_ORPHANS when orphans are detected."""
    from unittest.mock import patch

    with patch(
        "myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes",
        return_value=[{"pid": 9999, "name": "chrome"}],
    ):
        actions = await build_repair_actions([], [])

    browser_actions = [a for a in actions if a.action_id == RepairActionId.CLEANUP_BROWSER_ORPHANS]
    assert len(browser_actions) == 1
    assert browser_actions[0].executable is True
    assert browser_actions[0].component == "BrowserRuntime"
    assert "1 orphan" in browser_actions[0].description
    assert browser_actions[0].endpoint is not None


# ---------- Multiple orphan PIDs ----------


@pytest.mark.asyncio
async def test_execute_cleanup_browser_multiple_pids() -> None:
    """Multiple orphan PIDs should all be passed to cleanup_orphan_processes."""
    from unittest.mock import patch

    orphans = [{"pid": 100}, {"pid": 200}, {"pid": 300}]
    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=orphans):
        with patch(
            "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
            return_value={"killed": 3, "message": "killed 3", "failed": []},
        ) as mock_cleanup:
            result = await execute_repair_action(
                RepairActionId.CLEANUP_BROWSER_ORPHANS,
                RepairActionExecuteRequest(dry_run=False, confirm=True),
            )
    mock_cleanup.assert_called_once_with([100, 200, 300], force=True)
    assert result.status == "completed"
    assert result.changed is True
    assert result.details["killed"] == 3
    assert result.details["orphan_pids"] == [100, 200, 300]


# ---------- DLQ message field fallback ----------


@pytest.mark.asyncio
async def test_build_dlq_missing_message_field() -> None:
    """DLQ report without 'message' key should use fallback."""
    server_reports: list[dict[str, object]] = [{"component_name": "DLQ", "status": "fail"}]
    actions = await build_repair_actions([], server_reports)
    assert len(actions) == 1
    assert actions[0].action_id == RepairActionId.REVIEW_CHANNEL_DLQ
    assert "DLQ reported failed messages" in actions[0].reason


# ---------- cleanup_orphan_processes result missing 'message' key ----------


@pytest.mark.asyncio
async def test_execute_cleanup_browser_result_missing_message() -> None:
    """When cleanup result has no 'message' key, fallback message is used."""
    from unittest.mock import patch

    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=[{"pid": 555}]):
        with patch(
            "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
            return_value={"killed": 1, "failed": []},
        ):
            result = await execute_repair_action(
                RepairActionId.CLEANUP_BROWSER_ORPHANS,
                RepairActionExecuteRequest(dry_run=False, confirm=True),
            )
    assert result.status == "completed"
    assert "Processed 1 orphan browser process" in result.message


# ---------- Mixed orphans: some with pid, some without ----------

# ---------- detail field priority in reason ----------


@pytest.mark.asyncio
async def test_reason_uses_detail_when_present() -> None:
    """When detail is provided, reason should prefer detail over message."""
    reports = [_report("Network", "fail", message="Internet not available.", detail="DNS resolution timed out after 3s")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].reason == "DNS resolution timed out after 3s"


@pytest.mark.asyncio
async def test_reason_falls_back_to_message_when_no_detail() -> None:
    """When detail is None, reason should fall back to message."""
    reports = [_report("Network", "fail", message="Internet not available.")]
    actions = await build_repair_actions(reports, [])
    assert len(actions) == 1
    assert actions[0].reason == "Internet not available."


@pytest.mark.asyncio
async def test_execute_cleanup_browser_mixed_pid_presence() -> None:
    """Orphans list with mixed pid presence: only entries with 'pid' are processed."""
    from unittest.mock import patch

    orphans = [{"pid": 111}, {"name": "chrome_no_pid"}, {"pid": 222}]
    with patch("myrm_agent_harness.toolkits.browser.find_orphan_chromium_processes", return_value=orphans):
        with patch(
            "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
            return_value={"killed": 2, "message": "killed 2", "failed": []},
        ) as mock_cleanup:
            result = await execute_repair_action(
                RepairActionId.CLEANUP_BROWSER_ORPHANS,
                RepairActionExecuteRequest(dry_run=False, confirm=True),
            )
    mock_cleanup.assert_called_once_with([111, 222], force=True)
    assert result.details["orphan_pids"] == [111, 222]


# ---------- SQLite backup / restore actions ----------


@pytest.mark.asyncio
async def test_execute_sqlite_backup_dry_run() -> None:
    result = await execute_repair_action(
        RepairActionId.SQLITE_BACKUP_NOW,
        RepairActionExecuteRequest(dry_run=True, confirm=False),
    )
    assert result.status == "dry_run"
    assert result.changed is False
    assert result.dry_run is True


@pytest.mark.asyncio
async def test_execute_sqlite_backup_real(tmp_path) -> None:
    import sqlite3

    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    mgr = SQLiteBackupManager(db, db.parent / "sqlite_backups")
    with patch("app.services.repair.actions._get_sqlite_backup_manager", return_value=mgr):
        result = await execute_repair_action(
            RepairActionId.SQLITE_BACKUP_NOW,
            RepairActionExecuteRequest(dry_run=False, confirm=True),
        )

    assert result.status == "completed"
    assert result.changed is True
    assert "Backup created" in result.message
    assert result.details.get("file_name")
    assert result.details.get("size_bytes")


@pytest.mark.asyncio
async def test_execute_sqlite_backup_failure() -> None:
    from unittest.mock import patch

    with patch(
        "app.services.repair.actions._get_sqlite_backup_manager",
        side_effect=RuntimeError("disk full"),
    ):
        result = await execute_repair_action(
            RepairActionId.SQLITE_BACKUP_NOW,
            RepairActionExecuteRequest(dry_run=False, confirm=True),
        )

    assert result.status == "failed"
    assert "disk full" in result.message


@pytest.mark.asyncio
async def test_execute_sqlite_restore_dry_run(tmp_path) -> None:
    import sqlite3

    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    mgr = SQLiteBackupManager(db, db.parent / "sqlite_backups")
    mgr.create_backup()

    with patch("app.services.repair.actions._get_sqlite_backup_manager", return_value=mgr):
        result = await execute_repair_action(
            RepairActionId.SQLITE_RESTORE_LATEST,
            RepairActionExecuteRequest(dry_run=True, confirm=False),
        )

    assert result.status == "dry_run"
    assert result.changed is False
    assert "1 available" in result.message


@pytest.mark.asyncio
async def test_execute_sqlite_restore_requires_confirm(tmp_path) -> None:
    import sqlite3

    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    mgr = SQLiteBackupManager(db, db.parent / "sqlite_backups")
    with patch("app.services.repair.actions._get_sqlite_backup_manager", return_value=mgr):
        result = await execute_repair_action(
            RepairActionId.SQLITE_RESTORE_LATEST,
            RepairActionExecuteRequest(dry_run=False, confirm=False),
        )

    assert result.status == "confirmation_required"
    assert result.changed is False


@pytest.mark.asyncio
async def test_execute_sqlite_restore_confirmed(tmp_path) -> None:
    import sqlite3

    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    for i in range(20):
        conn.execute("INSERT INTO t VALUES (?)", (i,))
    conn.commit()
    conn.close()

    mgr = SQLiteBackupManager(db, db.parent / "sqlite_backups")
    mgr.create_backup()

    with patch("app.services.repair.actions._get_sqlite_backup_manager", return_value=mgr):
        result = await execute_repair_action(
            RepairActionId.SQLITE_RESTORE_LATEST,
            RepairActionExecuteRequest(dry_run=False, confirm=True),
        )

    assert result.status == "completed"
    assert result.changed is True

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    conn.close()
    assert count == 20


@pytest.mark.asyncio
async def test_execute_sqlite_restore_failure_no_backups(tmp_path) -> None:
    import sqlite3

    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    mgr = SQLiteBackupManager(db, db.parent / "sqlite_backups")
    with patch("app.services.repair.actions._get_sqlite_backup_manager", return_value=mgr):
        result = await execute_repair_action(
            RepairActionId.SQLITE_RESTORE_LATEST,
            RepairActionExecuteRequest(dry_run=False, confirm=True),
        )

    assert result.status == "failed"


def test_sqlite_backup_action_returns_action_when_db_exists(tmp_path) -> None:
    """_sqlite_backup_action returns a RepairAction when the DB file exists."""
    import sqlite3

    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        action = _original_sqlite_backup_action()

    assert action is not None
    assert action.action_id == RepairActionId.SQLITE_BACKUP_NOW
    assert action.executable is True
    assert action.risk_level == "low"


def test_sqlite_backup_action_returns_none_when_db_missing() -> None:
    """_sqlite_backup_action returns None when the DB file does not exist."""
    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.database.sqlite_path = "/nonexistent/path/db.sqlite"
        action = _original_sqlite_backup_action()

    assert action is None
