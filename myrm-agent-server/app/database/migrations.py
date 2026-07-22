"""数据库迁移脚本"""

import logging

from myrm_agent_harness.utils.db.migration_engine import (
    MigrationStatement,
    StatefulMigrationEngine,
)
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# 数据库迁移语句（按顺序执行）
# 已完成的迁移会被清理，新迁移添加到此列表
MIGRATION_STATEMENTS: list[str] = [
    "ALTER TABLE procedural_rules ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'user_extracted'",
    "ALTER TABLE cron_jobs ADD COLUMN delivery JSON",
    "ALTER TABLE cron_jobs ADD COLUMN agent_config TEXT",
    # Migrate delivery JSON from {mode,webhook_url,recipient_id} to {channel,target}
    """UPDATE cron_jobs SET delivery = json_object(
        'channel', json_extract(delivery, '$.mode'),
        'target', COALESCE(json_extract(delivery, '$.recipient_id'), json_extract(delivery, '$.webhook_url'))
    ) WHERE delivery IS NOT NULL AND json_extract(delivery, '$.mode') IS NOT NULL AND json_extract(delivery, '$.channel') IS NULL""",
    """CREATE TABLE IF NOT EXISTS channel_pairings (
        id VARCHAR(32) PRIMARY KEY,
        channel VARCHAR(50) NOT NULL,
        sender_id VARCHAR(255) NOT NULL,
        
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(channel, sender_id)
    )""",
    "ALTER TABLE agents ADD COLUMN model_selection JSON",
    # Chat history persistence for channel messages
    "ALTER TABLE chats ADD COLUMN source VARCHAR(50) NOT NULL DEFAULT 'web'",
    "ALTER TABLE chats ADD COLUMN channel_session_key VARCHAR(500)",
    "ALTER TABLE cron_jobs ADD COLUMN last_failure_alert_at TIMESTAMP",
    "ALTER TABLE cron_runs ADD COLUMN model VARCHAR(128)",
    "ALTER TABLE cron_runs ADD COLUMN usage_input_tokens INTEGER",
    "ALTER TABLE cron_runs ADD COLUMN usage_output_tokens INTEGER",
    "ALTER TABLE cron_runs ADD COLUMN usage_total_tokens INTEGER",
    "ALTER TABLE cron_runs ADD COLUMN delivery_status VARCHAR(20)",
    "ALTER TABLE cron_runs ADD COLUMN delivery_error TEXT",
    "ALTER TABLE cron_jobs ADD COLUMN timeout_seconds INTEGER DEFAULT 300",
    "ALTER TABLE cron_jobs ADD COLUMN misfire_grace_seconds INTEGER DEFAULT 300",
    "ALTER TABLE cron_jobs ADD COLUMN active_hours JSON",
    "ALTER TABLE cron_jobs ADD COLUMN failure_delivery JSON",
    "ALTER TABLE cron_jobs ADD COLUMN required_capabilities JSON",
    "ALTER TABLE cron_jobs ADD COLUMN allowed_roots JSON",
    "ALTER TABLE cron_jobs ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE cron_jobs ADD COLUMN retry_backoff_ms INTEGER NOT NULL DEFAULT 30000",
    "ALTER TABLE cron_jobs ADD COLUMN delete_after_run BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE cron_jobs ADD COLUMN deduplicate BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE cron_jobs ADD COLUMN last_output_hash VARCHAR(64)",
    "ALTER TABLE agents ADD COLUMN security_overrides JSON",
    "ALTER TABLE chats ADD COLUMN compacted_summary TEXT",
    "ALTER TABLE chats ADD COLUMN compacted_before_id VARCHAR(255)",
    "ALTER TABLE chats ADD COLUMN compacted_at TIMESTAMP",
    "ALTER TABLE chats ADD COLUMN compacted_tokens_saved INTEGER",
    "ALTER TABLE cron_runs ADD COLUMN metadata JSON",
    "ALTER TABLE cron_runs ADD COLUMN integrity_hash VARCHAR(64)",
    "ALTER TABLE cron_runs ADD COLUMN prev_hash VARCHAR(64)",
    """CREATE TABLE IF NOT EXISTS user_tool_allowlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        
        permission VARCHAR(255) NOT NULL,
        pattern VARCHAR(255) NOT NULL DEFAULT '*',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE( permission, pattern)
    )""",
    "ALTER TABLE user_tool_allowlist ADD COLUMN tool_name VARCHAR(255)",
    "ALTER TABLE user_tool_allowlist ADD COLUMN tool_args_hash VARCHAR(32)",
    """DROP INDEX IF EXISTS uq_user_permission_pattern""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_user_allowlist ON user_tool_allowlist( permission, pattern, tool_name, tool_args_hash)""",
    """DROP INDEX IF EXISTS uq_user_allowlist""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_user_allowlist_v2 ON user_tool_allowlist( permission, tool_name, tool_args_hash)""",
    """CREATE TABLE user_tool_allowlist_new AS SELECT id,  permission, tool_name, tool_args_hash, created_at FROM user_tool_allowlist""",
    """DROP TABLE user_tool_allowlist""",
    """ALTER TABLE user_tool_allowlist_new RENAME TO user_tool_allowlist""",
    """CREATE UNIQUE INDEX uq_user_allowlist_final ON user_tool_allowlist( permission, tool_name, tool_args_hash)""",
    """UPDATE user_tool_allowlist SET tool_name = '' WHERE tool_name IS NULL""",
    """UPDATE user_tool_allowlist SET tool_args_hash = '' WHERE tool_args_hash IS NULL""",
    "ALTER TABLE monitor_states ADD COLUMN last_reset_at TIMESTAMP",
    "ALTER TABLE monitor_states ADD COLUMN last_reset_reason VARCHAR(50)",
    # Cron job advanced scheduling fields
    "ALTER TABLE cron_jobs ADD COLUMN cooldown_seconds INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE cron_jobs ADD COLUMN max_fires INTEGER",
    "ALTER TABLE cron_jobs ADD COLUMN expires_at TIMESTAMP",
    "ALTER TABLE cron_jobs ADD COLUMN fire_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE cron_jobs ADD COLUMN session_target VARCHAR(20) NOT NULL DEFAULT 'isolated'",
    "ALTER TABLE cron_jobs ADD COLUMN failure_alert JSON",
    "ALTER TABLE cron_jobs ADD COLUMN run_retention_days INTEGER NOT NULL DEFAULT 30",
    "ALTER TABLE cron_jobs ADD COLUMN monitor_config JSON",
    "ALTER TABLE cron_jobs ADD COLUMN pre_condition_script TEXT",
    # Rebuild user_tool_allowlist with String PK (fix AUTOINCREMENT lost by CREATE TABLE AS SELECT)
    """CREATE TABLE IF NOT EXISTS user_tool_allowlist_v3 (
        id VARCHAR(32) PRIMARY KEY,
        
        permission VARCHAR(255) NOT NULL,
        tool_name VARCHAR(255) NOT NULL DEFAULT '',
        tool_args_hash VARCHAR(32) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE( permission, tool_name, tool_args_hash)
    )""",
    """INSERT INTO user_tool_allowlist_v3 (id,  permission, tool_name, tool_args_hash, created_at)
        SELECT CAST(id AS VARCHAR(32)),  permission,
               COALESCE(tool_name, ''), COALESCE(tool_args_hash, ''), created_at
        FROM user_tool_allowlist""",
    """DROP TABLE IF EXISTS user_tool_allowlist""",
    """ALTER TABLE user_tool_allowlist_v3 RENAME TO user_tool_allowlist""",
    # Session Notes persistence (real-time structured notes for zero-API compaction)
    "ALTER TABLE chats ADD COLUMN session_notes_json TEXT",
    # Batch Image Jobs — stateful orchestrator for multi-prompt generation
    """CREATE TABLE IF NOT EXISTS batch_image_jobs (
        id VARCHAR(32) PRIMARY KEY,
        
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        plan JSON,
        concurrency INTEGER NOT NULL DEFAULT 3,
        total_items INTEGER NOT NULL DEFAULT 0,
        completed_items INTEGER NOT NULL DEFAULT 0,
        failed_items INTEGER NOT NULL DEFAULT 0,
        estimated_cost VARCHAR(32),
        session_id VARCHAR(255),
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    )""",
    # Media Library — persistent gallery for AI-generated images/videos/audio
    """CREATE TABLE IF NOT EXISTS media_library (
        id VARCHAR(32) PRIMARY KEY,
        
        media_type VARCHAR(20) NOT NULL,
        source VARCHAR(50) NOT NULL DEFAULT 'generate',
        prompt TEXT,
        model VARCHAR(128),
        resolution VARCHAR(32),
        content_type VARCHAR(64) NOT NULL DEFAULT 'image/png',
        file_size INTEGER NOT NULL DEFAULT 0,
        storage_key VARCHAR(500) NOT NULL,
        thumbnail_key VARCHAR(500),
        tags JSON,
        session_id VARCHAR(255),
        batch_job_id VARCHAR(32),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE channel_pairings ADD COLUMN display_name VARCHAR(255)",
    "ALTER TABLE agents ADD COLUMN enabled_builtin_tools JSON",
    # Agent Profile 字段（Agent Management UI & CLI）
    "ALTER TABLE agents ADD COLUMN home_directory VARCHAR(500)",
    "ALTER TABLE agents ADD COLUMN is_built_in BOOLEAN NOT NULL DEFAULT 0",
    # Agent绑定到会话（支持统计和Conversation Forking）
    "ALTER TABLE chats ADD COLUMN agent_id VARCHAR(255) REFERENCES agents(id) ON DELETE SET NULL",
    # Agent name unique约束（user_id + name）
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_user_name ON agents( name)",
    # System Notifications
    """CREATE TABLE IF NOT EXISTS system_notifications (
        id VARCHAR(32) PRIMARY KEY,
        
        title VARCHAR(255) NOT NULL,
        message TEXT NOT NULL,
        type VARCHAR(20) NOT NULL,
        source VARCHAR(50) NOT NULL,
        is_read BOOLEAN NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "ALTER TABLE system_notifications ADD COLUMN meta_data JSON",
    # Message timestamp fields (sent_at, sent_timezone) for Prompt Cache stability
    "ALTER TABLE messages ADD COLUMN sent_at TIMESTAMP",
    "ALTER TABLE messages ADD COLUMN sent_timezone VARCHAR(64)",
    """UPDATE messages SET sent_at = created_at, sent_timezone = 'UTC' WHERE sent_at IS NULL""",
    # Agents table
    """CREATE TABLE IF NOT EXISTS agents (
        id VARCHAR(255) PRIMARY KEY,
        
        name VARCHAR(255) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        avatar VARCHAR(1000),
        model_config JSON NOT NULL DEFAULT '{}',
        system_prompt TEXT,
        skill_ids JSON NOT NULL DEFAULT '[]',
        mcp_servers JSON NOT NULL DEFAULT '[]',
        subagent_ids JSON NOT NULL DEFAULT '[]',
        workspace_policy VARCHAR(50) NOT NULL DEFAULT 'INHERIT_REQUESTER',
        memory_policy JSON,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        is_public BOOLEAN NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        enabled_builtin_tools JSON,
        home_directory VARCHAR(500),
        is_built_in BOOLEAN NOT NULL DEFAULT 0,
        security_overrides JSON,
        model_selection JSON,
        version INTEGER NOT NULL DEFAULT 1
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_user_name ON agents( name)",
    "ALTER TABLE agents ADD COLUMN subagent_ids JSON NOT NULL DEFAULT '[]'",
    "ALTER TABLE agents ADD COLUMN workspace_policy VARCHAR(50) NOT NULL DEFAULT 'INHERIT_REQUESTER'",
    "ALTER TABLE agents ADD COLUMN memory_policy JSON",
    "ALTER TABLE agents ADD COLUMN personality_style VARCHAR(32) NOT NULL DEFAULT 'professional'",
    "ALTER TABLE agents ADD COLUMN prompt_mode VARCHAR(20) NOT NULL DEFAULT 'full'",
    "ALTER TABLE agent_turns ADD COLUMN spawn_depth INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE agent_turns ADD COLUMN spawned_by VARCHAR(255)",
    "CREATE INDEX ix_agent_turns_spawned_by ON agent_turns(spawned_by)",
    # Agent Secrets table
    """CREATE TABLE IF NOT EXISTS agent_secrets (
        id VARCHAR(255) PRIMARY KEY,
        agent_id VARCHAR(255) NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
        secret_key VARCHAR(255) NOT NULL,
        secret_value TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, secret_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_agent_secrets_agent_id ON agent_secrets(agent_id)",
    # FTS5 Virtual Table (original V86-V90 — preserved for checksum stability).
    # These use content_rowid=id which is broken for UUID PKs, but V93-V101
    # at the end DROP and rebuild with the correct content_rowid=rowid.
    """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content,
        content=messages,
        content_rowid=id,
        tokenize='trigram'
    )""",
    """CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    """INSERT INTO messages_fts(rowid, content) SELECT id, content FROM messages WHERE id NOT IN (SELECT rowid FROM messages_fts)""",
    # Skill Version Management (Skill Optimization System)
    """CREATE TABLE IF NOT EXISTS skill_versions (
        skill_id VARCHAR(255) NOT NULL,
        version INTEGER NOT NULL,
        content TEXT NOT NULL,
        quality_score JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        created_by VARCHAR(50) NOT NULL DEFAULT 'llm',
        optimization_id VARCHAR(255),
        is_active BOOLEAN NOT NULL DEFAULT 0,
        metadata JSON,
        PRIMARY KEY (skill_id, version)
    )""",
    "ALTER TABLE agents ADD COLUMN max_iterations INTEGER",
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
]

# 创建索引的SQL语句列表
INDEX_STATEMENTS = [
    # 聊天表索引
    "CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chats_created_at ON chats(created_at DESC)",
    # 消息表索引
    "CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_chat_id_created_at ON messages(chat_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)",
    # Memory System 索引
    "CREATE INDEX IF NOT EXISTS idx_profile_attributes_key ON profile_attributes(key)",
    "CREATE INDEX IF NOT EXISTS idx_profile_attributes_user_key ON profile_attributes( key)",
    "CREATE INDEX IF NOT EXISTS idx_procedural_rules_priority ON procedural_rules(priority DESC)",
    "CREATE INDEX IF NOT EXISTS idx_procedural_rules_source ON procedural_rules(source)",
    "CREATE INDEX IF NOT EXISTS idx_pending_memories_status ON pending_memories(status)",
    # User Configs 索引
    "CREATE INDEX IF NOT EXISTS idx_user_configs_config_key ON user_configs(config_key)",
    "CREATE INDEX IF NOT EXISTS idx_user_configs_user_config_key ON user_configs( config_key)",
    # Agent Event System 索引 (Local Mode Only)
    "CREATE INDEX IF NOT EXISTS idx_agent_turns_chat_id ON agent_turns(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_turns_status ON agent_turns(status)",
    "CREATE INDEX IF NOT EXISTS idx_agent_turns_created_at ON agent_turns(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agent_events_turn_id ON agent_events(turn_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_events_event_type ON agent_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_agent_events_tool_name ON agent_events(tool_name)",
    "CREATE INDEX IF NOT EXISTS idx_agent_events_created_at ON agent_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_agent_events_turn_id_event_index ON agent_events(turn_id, event_index)",
    # Channel Pairings 索引
    "CREATE INDEX IF NOT EXISTS idx_channel_pairings_channel ON channel_pairings(channel)",
    "CREATE INDEX IF NOT EXISTS idx_channel_pairings_channel_sender ON channel_pairings(channel, sender_id)",
    # Chat channel session indexes
    "CREATE INDEX IF NOT EXISTS idx_chats_source ON chats(source)",
    "CREATE INDEX IF NOT EXISTS idx_chats_channel_session_key ON chats(channel_session_key)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_channel_session ON chats( channel_session_key)",
    # User Tool Allowlist 索引
    "CREATE INDEX IF NOT EXISTS idx_user_tool_allowlist_permission ON user_tool_allowlist(permission)",
    # Media Library 索引
    "CREATE INDEX IF NOT EXISTS idx_media_library_media_type ON media_library(media_type)",
    "CREATE INDEX IF NOT EXISTS idx_media_library_session_id ON media_library(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_media_library_batch_job_id ON media_library(batch_job_id)",
    "CREATE INDEX IF NOT EXISTS idx_media_library_created_at ON media_library(created_at DESC)",
    # Conversation Fork 表
    """CREATE TABLE IF NOT EXISTS conversation_forks (
        child_chat_id VARCHAR(255) PRIMARY KEY,
        parent_chat_id VARCHAR(255) NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        fork_checkpoint_id VARCHAR(255),
        fork_message_index INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    # Conversation Fork 索引
    "CREATE INDEX IF NOT EXISTS idx_fork_child_to_parent ON conversation_forks(child_chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_fork_parent_children ON conversation_forks(parent_chat_id)",
    # System Notifications 索引
    "CREATE INDEX IF NOT EXISTS idx_system_notifications_created_at ON system_notifications(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_system_notifications_is_read ON system_notifications(is_read)",
    # Message timestamp 索引
    "CREATE INDEX IF NOT EXISTS idx_messages_sent_at ON messages(sent_at)",
    # Skill Versions 索引 (Skill Optimization System)
    "CREATE INDEX IF NOT EXISTS idx_skill_versions_skill_id ON skill_versions(skill_id)",
    "CREATE INDEX IF NOT EXISTS idx_skill_versions_is_active ON skill_versions(skill_id, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_skill_versions_version_desc ON skill_versions(skill_id, version DESC)",
    "CREATE INDEX IF NOT EXISTS idx_skill_versions_created_at ON skill_versions(skill_id, created_at DESC)",
    # Shadow Sample 新增比对字段 (Skill Observability Enhancement)
    "ALTER TABLE skill_shadow_samples ADD COLUMN similarity_score REAL",
    "ALTER TABLE skill_shadow_samples ADD COLUMN diff_summary VARCHAR(500)",
    # Unified Approval FSM indexes
    "CREATE INDEX IF NOT EXISTS idx_approvals_user_status ON approvals( status)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_agent_id ON approvals(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_chat_id ON approvals(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_thread_id ON approvals(thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_action_type ON approvals(action_type)",
    "CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status)",
    "CREATE INDEX IF NOT EXISTS idx_experience_ledger_event_type ON experience_ledger_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_experience_ledger_entity_type ON experience_ledger_events(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_experience_ledger_entity_id ON experience_ledger_events(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_experience_ledger_lineage_id ON experience_ledger_events(lineage_id)",
    "CREATE INDEX IF NOT EXISTS idx_experience_ledger_created_at ON experience_ledger_events(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_shared_contexts_status ON shared_contexts(status)",
    "CREATE INDEX IF NOT EXISTS idx_shared_context_bindings_context_id ON shared_context_bindings(context_id)",
    "CREATE INDEX IF NOT EXISTS idx_shared_context_bindings_target ON shared_context_bindings(target_type, target_id)",
    "CREATE INDEX IF NOT EXISTS idx_shared_context_write_proposals_context ON shared_context_write_proposals(context_id)",
    "CREATE INDEX IF NOT EXISTS idx_shared_context_write_proposals_status ON shared_context_write_proposals(status)",
    "ALTER TABLE cron_jobs ADD COLUMN skip_if_active BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE cron_jobs ADD COLUMN pre_condition_script TEXT",
    # Sibling branching indexes
    "CREATE INDEX IF NOT EXISTS idx_messages_sibling_group ON messages(sibling_group_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_chat_is_active ON messages(chat_id, is_active)",
    "ALTER TABLE agents ADD COLUMN auto_restore_domains JSON",
    # Kanban indexes
    "CREATE INDEX IF NOT EXISTS idx_kanban_tasks_board_id ON kanban_tasks(board_id)",
    "CREATE INDEX IF NOT EXISTS idx_kanban_tasks_status ON kanban_tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_kanban_tasks_priority ON kanban_tasks(priority)",
    "CREATE INDEX IF NOT EXISTS idx_kanban_tasks_agent_id ON kanban_tasks(agent_id)",
    # Kanban edge indexes
    "CREATE INDEX IF NOT EXISTS idx_kanban_edges_parent ON kanban_task_edges(parent_task_id)",
    "CREATE INDEX IF NOT EXISTS idx_kanban_edges_child ON kanban_task_edges(child_task_id)",
    # Kanban GC acceleration indexes (composite for time-range queries on events/runs)
    "CREATE INDEX IF NOT EXISTS ix_kanban_events_task_created ON kanban_task_events(task_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_kanban_runs_task_started ON kanban_task_runs(task_id, started_at)",
    # Calendar indexes
    "CREATE INDEX IF NOT EXISTS idx_calendar_events_start_at ON calendar_events(start_at)",
    "CREATE INDEX IF NOT EXISTS idx_calendar_events_agent_id ON calendar_events(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_calendar_events_status ON calendar_events(status)",
    # Agent command bindings (Skill-bound slash commands)
    "ALTER TABLE agents ADD COLUMN command_bindings JSON",
    "ALTER TABLE kanban_tasks ADD COLUMN progress_note TEXT",
    # OpenAPI service configurations for zero-code REST API tool integration
    "ALTER TABLE agents ADD COLUMN openapi_services JSON",
    # Memory import transaction ledger
    """CREATE TABLE IF NOT EXISTS memory_import_batches (
        id VARCHAR(80) PRIMARY KEY,
        dry_run_id VARCHAR(64) NOT NULL,
        source VARCHAR(80) NOT NULL,
        status VARCHAR(24) NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        imported_count INTEGER NOT NULL DEFAULT 0,
        unmapped_count INTEGER NOT NULL DEFAULT 0,
        transaction_item_count INTEGER NOT NULL DEFAULT 0,
        diagnostic_status VARCHAR(24),
        diagnostic_run_id VARCHAR(80),
        diagnostic_failed_count INTEGER NOT NULL DEFAULT 0,
        rollback_status VARCHAR(24),
        rolled_back_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL,
        confirmed_at TIMESTAMP NOT NULL,
        rolled_back_at TIMESTAMP,
        metadata JSON
    )""",
    """CREATE TABLE IF NOT EXISTS memory_import_items (
        id VARCHAR(255) PRIMARY KEY,
        batch_id VARCHAR(80) NOT NULL REFERENCES memory_import_batches(id) ON DELETE CASCADE,
        memory_type VARCHAR(50) NOT NULL,
        status VARCHAR(24) NOT NULL,
        memory_ids JSON NOT NULL DEFAULT '[]',
        profile_key VARCHAR(255),
        profile_previous_value TEXT,
        profile_imported_value TEXT,
        profile_previous_value_present BOOLEAN NOT NULL DEFAULT 0,
        profile_imported_value_present BOOLEAN NOT NULL DEFAULT 0,
        rollback_status VARCHAR(24),
        rollback_error TEXT,
        created_at TIMESTAMP NOT NULL,
        rolled_back_at TIMESTAMP,
        metadata JSON
    )""",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_batches_dry_run ON memory_import_batches(dry_run_id)",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_batches_status_time ON memory_import_batches(status, confirmed_at)",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_batches_rollback_status ON memory_import_batches(rollback_status)",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_items_batch_id ON memory_import_items(batch_id)",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_items_batch_type ON memory_import_items(batch_id, memory_type)",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_items_batch_status ON memory_import_items(batch_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_memory_import_items_profile_key ON memory_import_items(profile_key)",
    "ALTER TABLE memory_import_items ADD COLUMN profile_previous_revision VARCHAR(128)",
    "ALTER TABLE memory_import_items ADD COLUMN profile_imported_revision VARCHAR(128)",
    # Agent Profile Snapshot
    """CREATE TABLE IF NOT EXISTS agent_profile_snapshots (
        id VARCHAR(255) PRIMARY KEY,
        agent_id VARCHAR(255) NOT NULL,
        snapshot_data JSON NOT NULL,
        reason VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS idx_agent_profile_snapshots_agent_id ON agent_profile_snapshots(agent_id)",
    # Config Audit Log
    """CREATE TABLE IF NOT EXISTS config_audit_logs (
        id VARCHAR(255) PRIMARY KEY,
        config_key VARCHAR(100) NOT NULL,
        previous_value JSON,
        new_value JSON NOT NULL,
        version VARCHAR(50) NOT NULL,
        device_id VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_config_audit_logs_config_key ON config_audit_logs(config_key)",
    "CREATE INDEX IF NOT EXISTS idx_config_audit_logs_created_at ON config_audit_logs(created_at)",
    # Memory Archive Restore ledger
    """CREATE TABLE IF NOT EXISTS memory_archive_restore_batches (
        id VARCHAR(80) PRIMARY KEY,
        source VARCHAR(80) NOT NULL DEFAULT 'myrm_archive',
        status VARCHAR(24) NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        plan_hash VARCHAR(64) NOT NULL,
        restored_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        conflict_count INTEGER NOT NULL DEFAULT 0,
        failed_count INTEGER NOT NULL DEFAULT 0,
        transaction_item_count INTEGER NOT NULL DEFAULT 0,
        rollback_status VARCHAR(24),
        rolled_back_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL,
        confirmed_at TIMESTAMP NOT NULL,
        rolled_back_at TIMESTAMP,
        metadata JSON
    )""",
    """CREATE TABLE IF NOT EXISTS memory_archive_restore_items (
        id VARCHAR(255) PRIMARY KEY,
        batch_id VARCHAR(80) NOT NULL REFERENCES memory_archive_restore_batches(id) ON DELETE CASCADE,
        section VARCHAR(40) NOT NULL,
        item_kind VARCHAR(80) NOT NULL,
        source_id VARCHAR(255),
        target_id VARCHAR(255),
        status VARCHAR(24) NOT NULL,
        rollback_status VARCHAR(24),
        rollback_error TEXT,
        created_at TIMESTAMP NOT NULL,
        rolled_back_at TIMESTAMP,
        metadata JSON
    )""",
    "CREATE INDEX IF NOT EXISTS ix_memory_archive_restore_batches_status_time ON memory_archive_restore_batches(status, confirmed_at)",
    "CREATE INDEX IF NOT EXISTS ix_memory_archive_restore_batches_rollback_status ON memory_archive_restore_batches(rollback_status)",
    "CREATE INDEX IF NOT EXISTS ix_memory_archive_restore_items_batch_section ON memory_archive_restore_items(batch_id, section)",
    "CREATE INDEX IF NOT EXISTS ix_memory_archive_restore_items_batch_status ON memory_archive_restore_items(batch_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_memory_archive_restore_items_target ON memory_archive_restore_items(item_kind, target_id)",
    "ALTER TABLE agents ADD COLUMN browser_engine VARCHAR(50)",
    "ALTER TABLE agents ADD COLUMN browser_source VARCHAR(20)",
    "ALTER TABLE agents ADD COLUMN dialog_policy VARCHAR(20)",
    "ALTER TABLE agents ADD COLUMN session_recording VARCHAR(20)",
    "ALTER TABLE agents ADD COLUMN cron_post_run_verify BOOLEAN NOT NULL DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS widget_kv (
        namespace VARCHAR(128) NOT NULL,
        key VARCHAR(256) NOT NULL,
        value TEXT NOT NULL,
        chat_id VARCHAR(36) NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (namespace, key)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_widget_kv_chat_id ON widget_kv(chat_id)",
    "DROP INDEX IF EXISTS idx_calendar_events_start_at",
    "DROP INDEX IF EXISTS idx_calendar_events_agent_id",
    "DROP INDEX IF EXISTS idx_calendar_events_status",
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
]


async def run_migrations(engine: AsyncEngine) -> None:
    """运行数据库迁移 (Zero-Ops Stateful Migration Engine)

    采用状态化迁移引擎，自动维护 _schema_migrations 表，
    提供精准计时、慢查询捕获和基线平滑升级能力。
    """
    migrations = [MigrationStatement(version=i, sql=stmt) for i, stmt in enumerate(MIGRATION_STATEMENTS)]

    migration_engine = StatefulMigrationEngine(
        engine=engine,
        table_name="_schema_migrations",
        baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='chats'",
        slow_threshold_ms=100.0,
    )

    report = await migration_engine.run_migrations(migrations)

    if report.failed_count > 0:
        logger.error(
            "❌ FATAL: Database migration failed at version %d.\nSQL: %s\nError: %s",
            report.failed_version,
            report.failed_sql,
            report.error_message,
        )
        raise RuntimeError(f"Database migration failed at version {report.failed_version}: {report.error_message}")

    if report.applied_count > 0:
        summary = f"Database migrations done: {report.applied_count} applied, {report.skipped_count} skipped in {report.total_duration_ms:.1f}ms."
        if report.slowest_migrations:
            slow_str = ", ".join([f"V{m[0]}: {m[2]:.1f}ms" for m in report.slowest_migrations[:3]])
            summary += f" (Slowest: {slow_str})"
        logger.info(summary)
    elif report.baselined:
        logger.info("Database migrations baselined for existing database.")
    else:
        logger.debug(
            "Database migrations verified: all %d skipped in %.1fms.",
            report.skipped_count,
            report.total_duration_ms,
        )


async def create_indexes(engine: AsyncEngine) -> None:
    """创建数据库索引 (Zero-Ops Stateful Migration Engine)

    采用状态化迁移引擎，自动维护 _schema_indexes 表。
    """
    indexes = [MigrationStatement(version=i, sql=stmt) for i, stmt in enumerate(INDEX_STATEMENTS)]

    index_engine = StatefulMigrationEngine(
        engine=engine,
        table_name="_schema_indexes",
        baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='chats'",
        slow_threshold_ms=100.0,
    )

    report = await index_engine.run_migrations(indexes)

    if report.failed_count > 0:
        logger.error(
            "❌ FATAL: Database index creation failed at version %d.\nSQL: %s\nError: %s",
            report.failed_version,
            report.failed_sql,
            report.error_message,
        )
        raise RuntimeError(f"Database index creation failed at version {report.failed_version}: {report.error_message}")

    if report.applied_count > 0:
        summary = f"Database indexes created: {report.applied_count} applied, {report.skipped_count} skipped in {report.total_duration_ms:.1f}ms."
        if report.slowest_migrations:
            slow_str = ", ".join([f"V{m[0]}: {m[2]:.1f}ms" for m in report.slowest_migrations[:3]])
            summary += f" (Slowest: {slow_str})"
        logger.info(summary)
    elif report.baselined:
        logger.info("Database indexes baselined for existing database.")
    else:
        logger.debug(
            "Database indexes verified: all %d skipped in %.1fms.",
            report.skipped_count,
            report.total_duration_ms,
        )

    # 在 baselined 的情况下（例如全新初始化或首个迁移），非 ORM 定义的结构（如 FTS5 和部分日志表）
    # 可能由于迁移被跳过而未创建，因此需要在此处做保底检查并创建。
    await ensure_raw_sql_schema(engine)


async def ensure_raw_sql_schema(engine: AsyncEngine) -> None:
    """Ensure raw SQL tables and triggers (not in ORM) exist."""
    from sqlalchemy import text

    from app.database.repositories.conversation_recall.sql import (
        CONVERSATION_RECALL_BOOTSTRAP_SQL,
        CONVERSATION_RECALL_SCHEMA_SQL,
        CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL,
    )

    raw_sql = [
        # System Health History
        """CREATE TABLE IF NOT EXISTS system_health_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            overall_status VARCHAR(10) NOT NULL,
            overall_score INTEGER NOT NULL,
            component_reports JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_system_health_timestamp ON system_health_history(timestamp DESC)",
        # FTS5 Virtual Table
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
        *CONVERSATION_RECALL_SCHEMA_SQL,
        CONVERSATION_RECALL_BOOTSTRAP_SQL,
        CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL,
    ]
    try:
        async with engine.begin() as conn:
            for sql in raw_sql:
                await conn.execute(text(sql))
        logger.debug("Raw SQL schema verification completed.")
    except Exception as e:
        logger.error("Failed to ensure raw SQL schema: %s", e)
