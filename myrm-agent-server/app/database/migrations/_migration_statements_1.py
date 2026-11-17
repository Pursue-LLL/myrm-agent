"""迁移语句清单第 1 段：``MIGRATION_STATEMENTS`` 的第 0 至 94 位。

[INPUT]
(none — released SQL statements)

[OUTPUT]
MIGRATION_STATEMENTS_1: 第 0 至 94 位的迁移语句，均已发布，不删、不改、不挪位

[POS]
database 层迁移语句。版本号是语句在整条清单里的下标，各段按文件序号首尾相接，所以段与段的边界、段内的先后都不能动。
"""

MIGRATION_STATEMENTS_1: list[str] = [
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
    # V223-V225: 对应 agent_turns 表列迁移的 no-op 占位。
    # agent_turns 表在当前 schema 中不存在（后续版本已 DROP），
    # 列表 APPEND-ONLY 且版本号由索引决定，删除会重排后续版本导致已迁移库跳过；
    # 故保持元素位置不变、替换为 no-op。
    "SELECT 1 -- agent_turns.spawn_depth column migration placeholder",
    "SELECT 1 -- agent_turns.spawned_by column migration placeholder",
    "SELECT 1 -- ix_agent_turns_spawned_by index migration placeholder",
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
]
