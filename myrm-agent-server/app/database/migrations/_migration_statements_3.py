"""迁移语句清单第 3 段：``MIGRATION_STATEMENTS`` 自第 180 位起，新语句追加在本文件末尾。

[INPUT]
app.database.migrations._sql_constants::九条冻结 SQL 常量 (POS: 遗留数据修复语句，本段按位置引用)
app.database.personality_style_merge::MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL (POS: 沟通风格并入 system_prompt 的冻结语句)

[OUTPUT]
MIGRATION_STATEMENTS_3: 第 180 位起的迁移语句

[POS]
database 层迁移语句，清单的最后一段。版本号是语句在整条清单里的下标，已发布的语句不删、不改、不挪位；
本文件接近 400 行时，新开 _migration_statements_4.py 接着追加，并在 __init__.py 的拼接处按顺序加入。
"""

from app.database.personality_style_merge import MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL

from ._sql_constants import (
    BACKFILL_LEGACY_WAKEUP_NOTICE_SQL,
    CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL,
    CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL,
    NORMALIZE_RETIRED_PROMPT_MODES_SQL,
    PAUSE_STALLED_ONCE_CRON_JOBS_SQL,
    REARM_STALLED_CRON_JOBS_SQL,
    REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL,
)

MIGRATION_STATEMENTS_3: list[str] = [
    CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL,
    "ALTER TABLE agents ADD COLUMN memory_extraction_preset VARCHAR(32) NOT NULL DEFAULT 'auto'",
    # V182: forward-fix for baselined DBs that predated session_access_roots at V128 insert.
    "ALTER TABLE chats ADD COLUMN session_access_roots JSON",
    # Dynamic Workflow binding on cron jobs (harness cron engine reads these columns).
    # IMPORTANT: MIGRATION_STATEMENTS / INDEX_STATEMENTS are APPEND-ONLY — never
    # insert/reorder statements in the middle of the list. Engine versions come from
    # enumerate(list_index); an insertion silently reuses prior version numbers and the
    # engine only warns (never re-runs) on checksum mismatch, permanently skipping the
    # displaced migration.
    "ALTER TABLE cron_jobs ADD COLUMN workflow_template_id VARCHAR(64)",
    "ALTER TABLE cron_jobs ADD COLUMN workflow_template_args JSON",
    # Per-task model override (KanbanPerTaskModelStrategyOverride)
    "ALTER TABLE kanban_tasks ADD COLUMN model_override VARCHAR(255)",
    # V186: kanban require_approval — moved here from INDEX_STATEMENTS where version
    # drift (V142) permanently skipped it (checksum mismatch; engine warns, never re-runs).
    # This is the single source of truth; INDEX_STATEMENTS no longer carries the DDL.
    "ALTER TABLE kanban_tasks ADD COLUMN require_approval BOOLEAN NOT NULL DEFAULT 0",
    # Per-agent default chat security preset (hitl/accept_edits/explore)
    "ALTER TABLE agents ADD COLUMN default_security_preset VARCHAR(20)",
    # Persist the 9th board setting (block_recurrence_limit): the dispatcher's
    # block→unblock→TRIAGE escalation threshold. New DBs get the column from
    # create_all; this append-only ALTER covers existing databases (the
    # migration engine skips duplicate-column errors idempotently).
    "ALTER TABLE kanban_boards ADD COLUMN block_recurrence_limit INTEGER NOT NULL DEFAULT 2",
    # Per-agent team roster discovery control: team leaders dynamically scan
    # agents with allow_discovery=True; column persisted here for existing DBs.
    "ALTER TABLE agents ADD COLUMN allow_discovery BOOLEAN NOT NULL DEFAULT 1",
    # Permission usage log needs user_id for audit: new DBs get the column from
    # create_all; this append-only ALTER covers existing databases (the
    # migration engine skips duplicate-column errors idempotently). The default
    # matches the harness session_id_var fallback ("default_session").
    "ALTER TABLE skill_permission_usage_logs ADD COLUMN user_id VARCHAR(255) NOT NULL DEFAULT 'default_session'",
    # Password-protected share rows persist their share_path (the token cannot be
    # rebuilt because the password is never stored); unprotected rows keep the
    # column NULL and rebuild the path on demand. New DBs get the column from
    # create_all; this append-only ALTER covers existing databases.
    "ALTER TABLE artifact_share_records ADD COLUMN share_path VARCHAR(512)",
    # Chat share revocation is per-token: the current active token fingerprint is
    # persisted on create and moved into the revoked-fingerprint set on revoke, so
    # recreating a share for the same chat can never resurrect an old revoked link.
    # New DBs get the columns from create_all; these append-only ALTERs cover
    # existing databases (the migration engine skips duplicate-column errors).
    "ALTER TABLE chats ADD COLUMN share_token_fingerprint VARCHAR(64)",
    "ALTER TABLE chats ADD COLUMN share_revoked_fingerprints JSON",
    # Chat share status query: the active share's expiry (unix seconds) and
    # password-protection flag are persisted on create so the GUI can display
    # the current share state and rebuild unprotected links deterministically.
    "ALTER TABLE chats ADD COLUMN share_token_expires_at INTEGER",
    "ALTER TABLE chats ADD COLUMN share_token_protected BOOLEAN",
    # agent_turns/agent_events 表不存在于当前 schema：agent 事件以 harness
    # JSONL event-log 为 SSOT，这两个表在全新库中不创建，此处为存量库清表。
    "DROP TABLE IF EXISTS agent_events",
    "DROP TABLE IF EXISTS agent_turns",
    # Hosted MCP / sub-agent allowlist scope: agent_id column + 5-column unique index.
    # New DBs get these from create_all; append-only ALTER covers existing databases.
    "ALTER TABLE user_tool_allowlist ADD COLUMN agent_id VARCHAR(255) NOT NULL DEFAULT ''",
    "DROP INDEX IF EXISTS uq_user_allowlist_final",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_user_allowlist_final
        ON user_tool_allowlist(permission, tool_name, tool_args_hash, command_pattern, agent_id)""",
    "ALTER TABLE user_tool_allowlist ADD COLUMN expires_at TIMESTAMP",
    "ALTER TABLE cron_jobs ADD COLUMN skill_ids JSON",
    "ALTER TABLE agents ADD COLUMN responsibility_scope TEXT",
    "ALTER TABLE agents ADD COLUMN owner_label VARCHAR(100)",
    "ALTER TABLE agents ADD COLUMN acceptance_criteria JSON",
    # Session tags (ChatModel.tags): new DBs get the column from create_all; existing DBs need it appended.
    "ALTER TABLE chats ADD COLUMN tags JSON NOT NULL DEFAULT '[]'",
    # message_filter_config.pii_mode has no ORM field: an existing NOT NULL column without a default rejects ORM inserts, so drop it.
    "ALTER TABLE message_filter_config DROP COLUMN pii_mode",
    # Manus Scheduled Tasks 2.0: project binding for cron_jobs
    "ALTER TABLE cron_jobs ADD COLUMN project_id VARCHAR(255) REFERENCES projects(id) ON DELETE SET NULL",
    # The message-filter admin tables have no ORM model or reader: the live filter reads MESSAGE_FILTER_ENABLED / ADMIN_API_KEYS.
    "DROP TABLE IF EXISTS message_filter_config",
    "DROP TABLE IF EXISTS message_filter_rules",
    "DROP TABLE IF EXISTS message_filter_audit",
    "DROP TABLE IF EXISTS message_filter_config_history",
    # Retired batch-optimization tables: no model, route or page reads or writes them.
    "DROP TABLE IF EXISTS batch_audit_logs",
    "DROP TABLE IF EXISTS batch_optimization_tasks",
    # The offline durable-task table has no model, route or startup hook that reads or writes it.
    "DROP TABLE IF EXISTS offline_durable_tasks",
    # No model, route or page reads or writes the shadow A/B tables or the per-version quality score.
    "DROP TABLE IF EXISTS skill_shadow_samples",
    "DROP TABLE IF EXISTS skill_ab_test_results",
    "DROP TABLE IF EXISTS skill_optimization_records",
    "DROP TABLE IF EXISTS skill_quality_history",
    "ALTER TABLE skill_versions DROP COLUMN quality_score",
    # Evolution proposals live in approval_records; no model, route or page reads or writes pending_evolutions.
    "DROP TABLE IF EXISTS pending_evolutions",
    # A risk rule only blocks, so neither table keeps an ``action`` column. A rule stored with another action held nothing:
    # it is disabled before the column goes, because left enabled it would hold messages its author never meant to hold.
    "UPDATE risk_rules SET is_enabled = 0 WHERE action != 'block'",
    "ALTER TABLE risk_rules DROP COLUMN action",
    "ALTER TABLE risk_hits DROP COLUMN action",
    # A hit log holds a position or the timeout marker, never the matched text (a key, a number, an address).
    """UPDATE risk_hits SET match_summary = ''
    WHERE match_summary != '' AND match_summary != '(matching timed out)' AND match_summary NOT LIKE 'chars:%'""",
    # Capability token ``code_interpreter_tool`` -> ``code_interpreter``, the permission type the security engine
    # matches; the old token matched no permission, so a job or profile that declared it never got the capability.
    """UPDATE cron_jobs SET required_capabilities = REPLACE(required_capabilities, '"code_interpreter_tool"', '"code_interpreter"')
    WHERE required_capabilities LIKE '%"code_interpreter_tool"%'""",
    """UPDATE agents SET security_overrides = REPLACE(security_overrides, '"code_interpreter_tool"', '"code_interpreter"')
    WHERE security_overrides LIKE '%"code_interpreter_tool"%'""",
    """UPDATE security_profiles SET config_json = REPLACE(config_json, '"code_interpreter_tool"', '"code_interpreter"')
    WHERE config_json LIKE '%"code_interpreter_tool"%'""",
    # The reason, kind and wake-up time of a block exist only while the task is blocked: clear them from a task that
    # sits in another column, where they would show a reason and a countdown for a block it no longer has.
    """UPDATE kanban_tasks SET blocked_reason = NULL, block_kind = NULL, scheduled_until = NULL
    WHERE status != 'blocked' AND (blocked_reason IS NOT NULL OR block_kind IS NOT NULL OR scheduled_until IS NOT NULL)""",
    # The runtime-meter ledgers (search quota, browser runtime, sandbox workload) have no model, route or page:
    # no production path ever wrote them.
    "DROP TABLE IF EXISTS search_quota_records",
    "DROP TABLE IF EXISTS browser_runtime_records",
    "DROP TABLE IF EXISTS sandbox_workload_records",
    "ALTER TABLE chats ADD COLUMN history_sync_token VARCHAR(64)",
    # Channel pairing role/quota: the ORM gained both fields without a migration, so every
    # SELECT on channel_pairings failed with "no such column: channel_pairings.role" and the
    # cron scheduler health endpoint answered 51002 ("Database operation failed"), which the
    # AppLayout banner rendered as "scheduler stopped".
    "ALTER TABLE channel_pairings ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'",
    "ALTER TABLE channel_pairings ADD COLUMN daily_quota INTEGER",
    # Columns the ORM declares on tables that predate them. Fresh databases get them from
    # create_all, but an existing database needs the ALTER or every query on the table dies
    # with "no such column" (the failure mode that turned the scheduler banner red).
    "ALTER TABLE agents ADD COLUMN mounted_skill_ids JSON",
    "ALTER TABLE agents ADD COLUMN memory_decay_profile VARCHAR(32) NOT NULL DEFAULT 'normal'",
    "ALTER TABLE agents ADD COLUMN engine_params JSON",
    "ALTER TABLE agents ADD COLUMN tool_gateway_config JSON",
    "ALTER TABLE kanban_boards ADD COLUMN specify_max_tokens INTEGER NOT NULL DEFAULT 6000",
    "ALTER TABLE kanban_boards ADD COLUMN auto_specify_on_create BOOLEAN NOT NULL DEFAULT 0",
    # CLI-native session ids of external agents, so a server restart resumes the same external conversation.
    # New DBs get the column from create_all; this append-only ALTER covers existing databases.
    "ALTER TABLE chats ADD COLUMN external_cli_sessions JSON",
    BACKFILL_LEGACY_WAKEUP_NOTICE_SQL,
    REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL,
    # Isolation comes from automatic file snapshots, so the git-worktree sandbox root is no longer stored.
    "ALTER TABLE chats DROP COLUMN sandbox_base_dir",
    CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL,
    # A communication style is now ordinary system-prompt text; this keeps the style of every custom agent that chose one.
    MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL,
    "ALTER TABLE agents DROP COLUMN personality_style",
    "ALTER TABLE agent_profile_history DROP COLUMN personality_style",
    NORMALIZE_RETIRED_PROMPT_MODES_SQL,
    # No model maps an agent's responsibility scope, owner label or acceptance criteria, and nothing reads or writes them.
    "ALTER TABLE agents DROP COLUMN responsibility_scope",
    "ALTER TABLE agents DROP COLUMN owner_label",
    "ALTER TABLE agents DROP COLUMN acceptance_criteria",
    REARM_STALLED_CRON_JOBS_SQL,
    PAUSE_STALLED_ONCE_CRON_JOBS_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL,
    # Cron runs no longer carry a hash chain, so the two hash columns of cron_runs are gone.
    "ALTER TABLE cron_runs DROP COLUMN integrity_hash",
    "ALTER TABLE cron_runs DROP COLUMN prev_hash",
]
