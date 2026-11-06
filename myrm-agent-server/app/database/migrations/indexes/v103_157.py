"""数据库索引迁移语句 V103–V157。

[POS]
数据库迁移账本的一部分；按版本区间连续切片，由 __init__.py 顺序拼接。
"""

from __future__ import annotations

STATEMENTS: list[str] = [
        """CREATE TABLE IF NOT EXISTS artifact_publications (
        id VARCHAR(36) PRIMARY KEY,
        artifact_id VARCHAR(36) NOT NULL,
        hosting_target_id VARCHAR(36) NOT NULL,
        publication_url VARCHAR(512),
        publication_status VARCHAR(50),
        publication_project_ref VARCHAR(255),
        publication_version_id VARCHAR(36),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        FOREIGN KEY(artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
        UNIQUE(artifact_id, hosting_target_id)
    )""",
        "CREATE INDEX IF NOT EXISTS idx_artifact_publications_artifact_id ON artifact_publications(artifact_id)",
        "CREATE INDEX IF NOT EXISTS idx_artifact_publications_target_id ON artifact_publications(hosting_target_id)",
        "ALTER TABLE chats DROP COLUMN task_adaptive_digest",
        "ALTER TABLE user_tool_allowlist ADD COLUMN command_pattern VARCHAR(512) NOT NULL DEFAULT ''",
        "DROP INDEX IF EXISTS uq_user_allowlist_final",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_user_allowlist_final
        ON user_tool_allowlist(permission, tool_name, tool_args_hash, command_pattern)""",
        """CREATE TABLE IF NOT EXISTS interrupted_turn_markers (
        id VARCHAR(255) PRIMARY KEY,
        chat_id VARCHAR(255) NOT NULL UNIQUE,
        user_message_id VARCHAR(255) NOT NULL,
        action_mode VARCHAR(50) NOT NULL DEFAULT 'fast',
        agent_id VARCHAR(255),
        serialized_params JSON,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
    )""",
        """CREATE TABLE IF NOT EXISTS turn_capability_metric_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type VARCHAR(40) NOT NULL,
        source VARCHAR(20) NOT NULL,
        context_key VARCHAR(128),
        count INTEGER NOT NULL DEFAULT 1,
        selected_skill_count INTEGER,
        selected_mcp_count INTEGER,
        effective_skill_count INTEGER,
        effective_mcp_count INTEGER,
        failure_reason VARCHAR(80),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""",
        "CREATE INDEX IF NOT EXISTS ix_turn_capability_metrics_created_at ON turn_capability_metric_events(created_at)",
        """CREATE INDEX IF NOT EXISTS ix_turn_capability_metrics_event_type_created_at
        ON turn_capability_metric_events(event_type, created_at)""",
        """CREATE INDEX IF NOT EXISTS ix_turn_capability_metrics_context_created_at
        ON turn_capability_metric_events(context_key, created_at)""",
        """CREATE TABLE IF NOT EXISTS expert_summon_metric_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type VARCHAR(40) NOT NULL,
        surface VARCHAR(32) NOT NULL,
        context_key VARCHAR(128),
        trigger VARCHAR(32),
        template_kind VARCHAR(16),
        from_search BOOLEAN,
        used_use_case BOOLEAN,
        query_length INTEGER,
        failure_reason VARCHAR(80),
        count INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""",
        "CREATE INDEX IF NOT EXISTS ix_expert_summon_metrics_created_at ON expert_summon_metric_events(created_at)",
        """CREATE INDEX IF NOT EXISTS ix_expert_summon_metrics_event_type_created_at
        ON expert_summon_metric_events(event_type, created_at)""",
        """CREATE INDEX IF NOT EXISTS ix_expert_summon_metrics_surface_created_at
        ON expert_summon_metric_events(surface, created_at)""",
        """CREATE INDEX IF NOT EXISTS ix_expert_summon_metrics_context_created_at
        ON expert_summon_metric_events(context_key, created_at)""",
        """CREATE TABLE IF NOT EXISTS assessment_import_metric_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type VARCHAR(40) NOT NULL,
        surface VARCHAR(40) NOT NULL,
        trigger VARCHAR(32) NOT NULL,
        context_key VARCHAR(128),
        failure_reason VARCHAR(80),
        count INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""",
        "CREATE INDEX IF NOT EXISTS ix_assessment_import_metrics_created_at ON assessment_import_metric_events(created_at)",
        """CREATE INDEX IF NOT EXISTS ix_assessment_import_metrics_event_type_created_at
        ON assessment_import_metric_events(event_type, created_at)""",
        """CREATE INDEX IF NOT EXISTS ix_assessment_import_metrics_surface_created_at
        ON assessment_import_metric_events(surface, created_at)""",
        """CREATE INDEX IF NOT EXISTS ix_assessment_import_metrics_trigger_created_at
        ON assessment_import_metric_events(trigger, created_at)""",
        """CREATE INDEX IF NOT EXISTS ix_assessment_import_metrics_context_created_at
        ON assessment_import_metric_events(context_key, created_at)""",
        "ALTER TABLE projects ADD COLUMN default_agent_id VARCHAR(255) REFERENCES agents(id) ON DELETE SET NULL",
        "ALTER TABLE kanban_tasks ADD COLUMN goal_mode BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE kanban_tasks ADD COLUMN goal_max_turns INTEGER",
        "ALTER TABLE chats ADD COLUMN active_moa_preset_id VARCHAR(50)",
        "UPDATE chats SET action_mode = 'agent' WHERE action_mode = 'consensus'",
        "ALTER TABLE chats ADD COLUMN compaction_failure_cooldown_until TIMESTAMP",
        "ALTER TABLE chats ADD COLUMN compaction_failure_error VARCHAR(500)",
        "ALTER TABLE chats ADD COLUMN compression_ineffective_streak INTEGER NOT NULL DEFAULT 0",
        """CREATE TABLE IF NOT EXISTS batch_directory_projects (
        id VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        prompt TEXT NOT NULL DEFAULT '',
        board_id VARCHAR(32) REFERENCES kanban_boards(id) ON DELETE SET NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        concurrency INTEGER NOT NULL DEFAULT 3,
        agent_id VARCHAR(255),
        model_override VARCHAR(255),
        max_runtime_seconds INTEGER,
        require_approval BOOLEAN NOT NULL DEFAULT 0,
        notify_enabled BOOLEAN NOT NULL DEFAULT 1,
        directories JSON,
        artifact_patterns JSON,
        total_tasks INTEGER NOT NULL DEFAULT 0,
        completed_tasks INTEGER NOT NULL DEFAULT 0,
        failed_tasks INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    )""",
        "CREATE INDEX IF NOT EXISTS ix_batch_directory_projects_board ON batch_directory_projects(board_id)",
        "CREATE INDEX IF NOT EXISTS ix_batch_directory_projects_status ON batch_directory_projects(status)",
        "ALTER TABLE kanban_task_runs ADD COLUMN token_usage JSON",
        "ALTER TABLE kanban_task_runs ADD COLUMN cost_usd FLOAT",
        "ALTER TABLE shared_contexts ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'team'",
        "ALTER TABLE shared_contexts ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE shared_contexts ADD COLUMN last_accessed_at TIMESTAMP",
        "ALTER TABLE interrupted_turn_markers ADD COLUMN message_id VARCHAR(255) NOT NULL DEFAULT ''",
        "ALTER TABLE interrupted_turn_markers ADD COLUMN pending_steering_messages JSON",
        "ALTER TABLE user_tool_allowlist ADD COLUMN expires_at TIMESTAMP",
        """CREATE TABLE IF NOT EXISTS search_quota_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider VARCHAR(64) NOT NULL,
        year_month VARCHAR(7) NOT NULL,
        quota_limit INTEGER NOT NULL DEFAULT 1000,
        used_count INTEGER NOT NULL DEFAULT 0,
        is_depleted BOOLEAN NOT NULL DEFAULT 0,
        is_metered BOOLEAN NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_search_quota_provider_month ON search_quota_records(provider, year_month)",
        """CREATE TABLE IF NOT EXISTS browser_runtime_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id VARCHAR(128) NOT NULL,
        start_time FLOAT NOT NULL,
        end_time FLOAT,
        duration_seconds FLOAT NOT NULL DEFAULT 0.0,
        status VARCHAR(32) NOT NULL DEFAULT 'running',
        network_requests_count INTEGER NOT NULL DEFAULT 0,
        network_bytes_downloaded INTEGER NOT NULL DEFAULT 0,
        network_bytes_uploaded INTEGER NOT NULL DEFAULT 0,
        recording_saved BOOLEAN NOT NULL DEFAULT 0,
        recording_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
        "CREATE INDEX IF NOT EXISTS idx_browser_runtime_session ON browser_runtime_records(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_browser_runtime_status ON browser_runtime_records(status)",
        """CREATE TABLE IF NOT EXISTS a2a_peers (
        id VARCHAR(36) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        base_url VARCHAR(1024) NOT NULL,
        description TEXT,
        auth_type VARCHAR(32) NOT NULL DEFAULT 'bearer',
        encrypted_auth_token TEXT,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        last_probed_at TIMESTAMP,
        last_probe_status VARCHAR(32),
        last_probe_error TEXT,
        cached_card_json JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
        "CREATE INDEX IF NOT EXISTS idx_a2a_peers_base_url ON a2a_peers(base_url)",
        "ALTER TABLE agents ADD COLUMN a2a_enabled BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE agents ADD COLUMN a2a_trusted_peer_ids JSON",
        "ALTER TABLE agents ADD COLUMN trusted_desktop_apps JSON",
        "CREATE INDEX IF NOT EXISTS idx_cron_jobs_project_id ON cron_jobs(project_id)",
        "DROP INDEX IF EXISTS idx_a2a_peers_base_url",
        "DROP TABLE IF EXISTS a2a_peers",
]
