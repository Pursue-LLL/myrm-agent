"""Table layout, additive migrations and journal retention of the Dev Gate store."""

from __future__ import annotations

DEFAULT_JOURNAL_RETENTION_SEC: float = 7 * 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    owner_pid INTEGER NOT NULL,
    owner_token TEXT NOT NULL,
    owner_process_start TEXT NOT NULL DEFAULT '',
    owner_boot_id TEXT NOT NULL DEFAULT '',
    test_node_id TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    access_scope TEXT NOT NULL,
    workload TEXT NOT NULL,
    namespace TEXT NOT NULL,
    priority INTEGER NOT NULL,
    private_credits INTEGER NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    submitted_at REAL NOT NULL,
    phase_started_at REAL NOT NULL,
    last_progress_at REAL NOT NULL,
    hard_deadline REAL NOT NULL,
    node_started_at REAL NOT NULL,
    current_node TEXT NOT NULL,
    browser_context_id TEXT NOT NULL,
    page_ids_json TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    runtime_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    failure_token TEXT NOT NULL,
    pytest_evidence_hash TEXT NOT NULL DEFAULT '',
    cleanup_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_state_idx ON sessions(state, submitted_at);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    detail_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_session_idx ON events(session_id, event_id);
CREATE TABLE IF NOT EXISTS ownership_resources (
    session_id TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    resource_value TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (session_id, resource_key)
);
CREATE INDEX IF NOT EXISTS ownership_resources_session_idx
ON ownership_resources(session_id, updated_at);
"""

MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE sessions ADD COLUMN owner_process_start TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE sessions ADD COLUMN owner_boot_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE sessions ADD COLUMN pytest_evidence_hash TEXT NOT NULL DEFAULT ''",
)
