"""迁移语句清单第 2 段：``MIGRATION_STATEMENTS`` 的第 95 至 179 位。

[INPUT]
(none — released SQL statements)

[OUTPUT]
MIGRATION_STATEMENTS_2: 第 95 至 179 位的迁移语句，均已发布，不删、不改、不挪位

[POS]
database 层迁移语句。版本号是语句在整条清单里的下标，各段按文件序号首尾相接，所以段与段的边界、段内的先后都不能动。
"""

MIGRATION_STATEMENTS_2: list[str] = [
    # V93-V101: Fix FTS5 schema — rebuild with correct content_rowid=rowid
    # Existing databases may have broken FTS5 table (content_rowid=id with TEXT UUID)
    # which causes 'datatype mismatch' on every INSERT, corrupting the AFTER trigger.
    "DROP TRIGGER IF EXISTS messages_fts_insert",
    "DROP TRIGGER IF EXISTS messages_fts_delete",
    "DROP TRIGGER IF EXISTS messages_fts_update",
    "DROP TABLE IF EXISTS messages_fts",
    """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content,
        content=messages,
        content_rowid=rowid,
        tokenize='trigram'
    )""",
    """CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
        INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
    END""",
    """INSERT INTO messages_fts(messages_fts) VALUES('rebuild')""",
    # Cron job agent binding: add agent_id, drop unused agent_config
    "ALTER TABLE cron_jobs ADD COLUMN agent_id VARCHAR(255)",
    "CREATE INDEX IF NOT EXISTS idx_cron_jobs_agent_id ON cron_jobs(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_cron_jobs_chat_id ON cron_jobs(chat_id)",
    # Trigger system: per-job trigger configs + run trigger_source tracking
    "ALTER TABLE cron_jobs ADD COLUMN triggers JSON",
    "ALTER TABLE cron_runs ADD COLUMN trigger_source VARCHAR(20)",
    # Unified Approval FSM: replaces SkillDraft and scattered memory taint logic
    """CREATE TABLE IF NOT EXISTS approvals (
        id VARCHAR(255) PRIMARY KEY,
        
        agent_id VARCHAR(255) NOT NULL,
        chat_id VARCHAR(255),
        thread_id VARCHAR(255),
        action_type VARCHAR(50) NOT NULL,
        reason TEXT,
        severity VARCHAR(20) NOT NULL DEFAULT 'warning',
        payload JSON NOT NULL DEFAULT '{}',
        status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
        resolved_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS experience_ledger_events (
        id VARCHAR(32) PRIMARY KEY,
        
        namespace VARCHAR(100) NOT NULL DEFAULT 'default',
        event_type VARCHAR(100) NOT NULL,
        entity_type VARCHAR(50) NOT NULL,
        entity_id VARCHAR(255) NOT NULL,
        lineage_id VARCHAR(255) NOT NULL,
        parent_event_id VARCHAR(32),
        outcome VARCHAR(50),
        summary TEXT NOT NULL DEFAULT '',
        artifact_refs JSON NOT NULL DEFAULT '{}',
        metrics_snapshot JSON NOT NULL DEFAULT '{}',
        detail JSON NOT NULL DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE approvals ADD COLUMN expires_at TIMESTAMP",
    "ALTER TABLE chats ADD COLUMN ephemeral_subagents JSON",
    "ALTER TABLE chats ADD COLUMN task_adaptive_digest TEXT",
    "ALTER TABLE chats ADD COLUMN session_loaded_skill_names JSON",
    # System Health History (健康趋势图数据存储)
    """CREATE TABLE IF NOT EXISTS system_health_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        overall_status VARCHAR(10) NOT NULL,
        overall_score INTEGER NOT NULL,
        component_reports JSON NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_system_health_timestamp ON system_health_history(timestamp DESC)",
    # Memory import dry-run review sessions
    """CREATE TABLE IF NOT EXISTS memory_import_dry_runs (
        id VARCHAR(64) PRIMARY KEY,
        source VARCHAR(80) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        payload_hash VARCHAR(64) NOT NULL,
        normalized_data JSON NOT NULL DEFAULT '{}',
        summary JSON NOT NULL DEFAULT '{}',
        warnings JSON NOT NULL DEFAULT '[]',
        created_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        confirmed_at TIMESTAMP,
        import_batch_id VARCHAR(80),
        metadata JSON
    )""",
    "CREATE INDEX IF NOT EXISTS idx_memory_import_dry_runs_source ON memory_import_dry_runs(source)",
    "CREATE INDEX IF NOT EXISTS idx_memory_import_dry_runs_status ON memory_import_dry_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_memory_import_dry_runs_payload_hash ON memory_import_dry_runs(payload_hash)",
    "CREATE INDEX IF NOT EXISTS idx_memory_import_dry_runs_expires_at ON memory_import_dry_runs(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_memory_import_dry_runs_import_batch_id ON memory_import_dry_runs(import_batch_id)",
    # Shared Context memory governance
    """CREATE TABLE IF NOT EXISTS shared_contexts (
        id VARCHAR(64) PRIMARY KEY,
        namespace VARCHAR(128) NOT NULL UNIQUE,
        name VARCHAR(120) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        policy JSON NOT NULL DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS shared_context_bindings (
        id VARCHAR(32) PRIMARY KEY,
        context_id VARCHAR(64) NOT NULL REFERENCES shared_contexts(id) ON DELETE CASCADE,
        target_type VARCHAR(32) NOT NULL,
        target_id VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(context_id, target_type, target_id)
    )""",
    """CREATE TABLE IF NOT EXISTS shared_context_write_proposals (
        id VARCHAR(32) PRIMARY KEY,
        context_id VARCHAR(64) NOT NULL REFERENCES shared_contexts(id) ON DELETE CASCADE,
        memory_type VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        metadata JSON,
        source_type VARCHAR(50) NOT NULL DEFAULT 'manual',
        source_id VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP
    )""",
    "ALTER TABLE cron_jobs ADD COLUMN context_from JSON",
    # Per-chat working directory for agent CWD and sandbox boundary
    "ALTER TABLE chats ADD COLUMN workspace_dir VARCHAR(1024)",
    "ALTER TABLE chats ADD COLUMN session_access_roots JSON",
    # Sibling branching: multiple regenerated responses for the same user query
    "ALTER TABLE messages ADD COLUMN sibling_group_id VARCHAR(255)",
    "ALTER TABLE messages ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
    # Catchup feature
    "ALTER TABLE chats ADD COLUMN last_read_at TIMESTAMP",
    "ALTER TABLE agents ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE agents ADD COLUMN skill_configs JSON NOT NULL DEFAULT '{}'",
    # Kanban board and task tables
    """CREATE TABLE IF NOT EXISTS kanban_boards (
        id VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        max_concurrent_tasks INTEGER NOT NULL DEFAULT 3,
        heartbeat_interval_seconds INTEGER NOT NULL DEFAULT 30,
        zombie_timeout_seconds INTEGER NOT NULL DEFAULT 120,
        max_retries_per_task INTEGER NOT NULL DEFAULT 3,
        auto_block_after_consecutive_failures INTEGER NOT NULL DEFAULT 5,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS kanban_tasks (
        id VARCHAR(32) PRIMARY KEY,
        board_id VARCHAR(32) NOT NULL REFERENCES kanban_boards(id) ON DELETE CASCADE,
        title VARCHAR(500) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status VARCHAR(20) NOT NULL DEFAULT 'backlog',
        priority VARCHAR(20) NOT NULL DEFAULT 'normal',
        agent_id VARCHAR(255),
        goal_id VARCHAR(255),
        require_approval BOOLEAN NOT NULL DEFAULT 0,
        parent_task_id VARCHAR(32) REFERENCES kanban_tasks(id) ON DELETE SET NULL,
        retry_count INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        last_heartbeat_at TIMESTAMP,
        blocked_reason TEXT,
        result TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )""",
    # Kanban task dependency edges (DAG)
    """CREATE TABLE IF NOT EXISTS kanban_task_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_task_id VARCHAR(32) NOT NULL REFERENCES kanban_tasks(id) ON DELETE CASCADE,
        child_task_id VARCHAR(32) NOT NULL REFERENCES kanban_tasks(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(parent_task_id, child_task_id)
    )""",
    # Calendar events
    """CREATE TABLE IF NOT EXISTS calendar_events (
        id VARCHAR(32) PRIMARY KEY,
        title VARCHAR(500) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        location VARCHAR(500),
        start_at TIMESTAMP NOT NULL,
        end_at TIMESTAMP,
        all_day BOOLEAN NOT NULL DEFAULT 0,
        rrule VARCHAR(500),
        color VARCHAR(20),
        source VARCHAR(50) NOT NULL DEFAULT 'manual',
        agent_id VARCHAR(255),
        chat_id VARCHAR(255),
        reminder_minutes INTEGER,
        status VARCHAR(20) NOT NULL DEFAULT 'confirmed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE chats ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE chats ADD COLUMN pin_order INTEGER NOT NULL DEFAULT 0",
    # Team Agent: agent_type distinguishes individual agents from team leaders
    "ALTER TABLE agents ADD COLUMN agent_type VARCHAR(20) NOT NULL DEFAULT 'individual'",
    # Chat soft-delete: NULL = active, non-NULL = trashed
    "ALTER TABLE chats ADD COLUMN deleted_at TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS idx_chats_deleted_at ON chats(deleted_at)",
    # Agent suggestion prompts (Empty State custom prompts per agent)
    "ALTER TABLE agents ADD COLUMN suggestion_prompts JSON",
    # Project grouping for chat organization
    "ALTER TABLE chats ADD COLUMN project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_chats_project_id ON chats(project_id)",
    "ALTER TABLE kanban_tasks ADD COLUMN max_runtime_seconds INTEGER",
    "ALTER TABLE kanban_tasks ADD COLUMN extra_skill_ids JSON",
    # BlockKind semantics for BLOCKED tasks (HUMAN / SCHEDULED / EXTERNAL)
    "ALTER TABLE kanban_tasks ADD COLUMN block_kind VARCHAR(20)",
    "ALTER TABLE kanban_tasks ADD COLUMN scheduled_until TIMESTAMP",
    "ALTER TABLE kanban_tasks ADD COLUMN attachment_ids JSON",
    # M-01: Per-agent MCP tool-level whitelist {server_name: [tool_name, ...]}
    "ALTER TABLE agents ADD COLUMN mcp_tool_selections JSON",
    "ALTER TABLE agents ADD COLUMN session_policy JSON",
    # Kanban worktree isolation: board-level default workspace + task-level workspace/branch
    "ALTER TABLE kanban_boards ADD COLUMN default_workdir VARCHAR(1024)",
    "ALTER TABLE kanban_tasks ADD COLUMN workspace_path VARCHAR(1024)",
    "ALTER TABLE kanban_tasks ADD COLUMN branch VARCHAR(255)",
    # Notification targets for channel_notify_tool (CU-07)
    "ALTER TABLE agents ADD COLUMN notify_targets JSON",
    # Block cycling diagnostic: tracks how many times an agent has blocked a task
    "ALTER TABLE kanban_tasks ADD COLUMN block_cycle_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE chats ADD COLUMN is_incognito BOOLEAN DEFAULT 0 NOT NULL;",
    # Project workspace path for multi-agent collaboration
    "ALTER TABLE projects ADD COLUMN workspace_path VARCHAR(1024)",
    # Sandbox worktree: stores original workspace path when sandbox is active
    "ALTER TABLE chats ADD COLUMN sandbox_base_dir VARCHAR(1024)",
    # Drop calendar_events table; calendar reads use Google Workspace OAuth + prebuilt skills.
    "DROP TABLE IF EXISTS calendar_events",
    # Drop legacy canvas table (no ORM; product module not shipped).
    "DROP TABLE IF EXISTS canvas",
    # Project milestone system
    "ALTER TABLE projects ADD COLUMN description TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE projects ADD COLUMN goal_summary TEXT NOT NULL DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS project_milestones (
        id VARCHAR(32) PRIMARY KEY,
        project_id VARCHAR(255) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title VARCHAR(500) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        sort_order INTEGER NOT NULL DEFAULT 0,
        acceptance_criteria TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS ix_milestones_project_status ON project_milestones(project_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_milestones_project_order ON project_milestones(project_id, sort_order)",
    "ALTER TABLE kanban_boards ADD COLUMN project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL",
    "ALTER TABLE kanban_boards ADD COLUMN milestone_id VARCHAR(32) REFERENCES project_milestones(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_kanban_boards_project_id ON kanban_boards(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_kanban_boards_milestone_id ON kanban_boards(milestone_id)",
    """CREATE TABLE IF NOT EXISTS assessment_import_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id VARCHAR(255) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        artifact_id VARCHAR(255) NOT NULL,
        artifact_version_id VARCHAR(255) NOT NULL,
        source_chat_id VARCHAR(255),
        status VARCHAR(20) NOT NULL DEFAULT 'reserved',
        total_milestones INTEGER NOT NULL DEFAULT 0,
        total_tasks INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_id, artifact_version_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_assessment_import_project_created_at ON assessment_import_ledger(project_id, created_at)",
    """CREATE TABLE IF NOT EXISTS web_push_subscriptions (
        endpoint_hash VARCHAR(32) PRIMARY KEY,
        endpoint TEXT NOT NULL,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        user_agent VARCHAR(512) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE chats ADD COLUMN share_revoked_at TIMESTAMP",
    "ALTER TABLE kanban_tasks DROP COLUMN goal_id",
    "ALTER TABLE cron_jobs ADD COLUMN tools_allowed JSON",
    "ALTER TABLE cron_jobs ADD COLUMN acceptance_criteria JSON",
    "ALTER TABLE wiki_evidence_metric_events ADD COLUMN context_key VARCHAR(128)",
]
