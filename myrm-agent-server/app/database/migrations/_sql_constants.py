"""遗留数据修复用的冻结 SQL 语句常量。

[INPUT]
(none — frozen SQL constants)

[OUTPUT]
CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL（项目里指向不存在沙箱目录的历史假工作区路径清空） / BACKFILL_LEGACY_WAKEUP_NOTICE_SQL（没有标记的后台完成通知行补 followup 标记） / REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL（遗留的循环守卫暂停 PENDING 审批行置为 REJECTED） / CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL（快速 / 深度搜索预置体行里的记忆策略覆盖清空） / NORMALIZE_RETIRED_PROMPT_MODES_SQL（已退役的 lean / naked 提示词模式行改为 full） / REARM_STALLED_CRON_JOBS_SQL（启用却无下一时刻的周期任务重订） / PAUSE_STALLED_ONCE_CRON_JOBS_SQL（同样停摆的一次性任务置为暂停） / STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL（智能体参数里已退役的回复语体键移除） / STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL（回滚快照里的同一键移除）

[POS]
database 层迁移语句常量：每条常量在 MIGRATION_STATEMENTS 里占一个位置，是一次性的数据修复。语句文本是迁移账本的校验源，
已执行的库依赖它的字节稳定，因此冻结在此，与会继续追加的清单分开。
"""

# Legacy auto-generated project workspace paths pointed at non-existent sandbox dirs.
# Users must re-bind via Mount Wizard after this one-time cleanup.
CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL = (
    "UPDATE projects SET workspace_path = NULL WHERE workspace_path LIKE '/persistent/workspace/project_%'"
)

# A user row whose id starts with ``wakeup_`` is a wake notice; one without the ``wakeup_notice`` marker is a followup
# notice (the wake it started always ran), so it gets that marker and every reader that skips notices recognises it.
# Selecting the prefix as an id range (up to the character after ``_``) scans the primary key instead of the table,
# and a row that already has a marker is left alone.
BACKFILL_LEGACY_WAKEUP_NOTICE_SQL = (
    "UPDATE messages "
    "SET extra_data = json_set(CASE WHEN json_type(extra_data) = 'object' THEN extra_data ELSE '{}' END, "
    "'$.wakeup_notice', 'followup') "
    "WHERE role = 'user' AND id >= 'wakeup_' AND id < 'wakeup`' "
    "AND json_extract(extra_data, '$.wakeup_notice') IS NULL"
)

# A loop-guard pause (``action_type`` ``tool_stuck``) is not an approval and gets no approval row, so a PENDING row of
# that type is a leftover: it has no ``expires_at``, no expiry sweep reaches it, and it keeps its chat refusing new
# messages. Rejecting it frees the chat; only PENDING rows of that exact action type change.
REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL = (
    "UPDATE approvals SET status = 'REJECTED', resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
    "WHERE action_type = 'tool_stuck' AND status = 'PENDING'"
)

# The built-in search agents run on the default memory policy and carry no override of their own; a row that
# still holds one is cleared. Only these two ids change: every other agent keeps the policy it has.
CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL = (
    "UPDATE agents SET memory_policy = NULL WHERE id IN ('builtin-fast-search', 'builtin-deep-search')"
)

# The prompt mode is set by the system (``search`` for the built-in search agents, ``full`` for every other agent); the
# two modes that a user could once pick, ``lean`` and ``naked``, no longer exist and become ``full``.
NORMALIZE_RETIRED_PROMPT_MODES_SQL = "UPDATE agents SET prompt_mode = 'full' WHERE prompt_mode IN ('lean', 'naked')"

# An enabled recurring job without a next run time is never run: nothing books a job that has no next slot. It is
# booked as due in 1970, so the startup recovery finds it past its grace, books its real next slot, records a skip and
# starts no run nobody asked for. ``updated_at`` marks the upgrade, so no slot before it is replayed. A job that has a
# next run time is left alone, and a second pass finds nothing to change.
REARM_STALLED_CRON_JOBS_SQL = (
    "UPDATE cron_jobs "
    "SET next_run_at = '1970-01-01 00:00:00.000000', updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now') "
    "WHERE status = 'active' AND next_run_at IS NULL AND json_extract(schedule, '$.kind') != 'once'"
)

# An enabled one-time job without a next run time has no moment to run at; pausing it shows its owner that it needs a
# new time instead of leaving it enabled and silent.
PAUSE_STALLED_ONCE_CRON_JOBS_SQL = (
    "UPDATE cron_jobs SET status = 'paused' "
    "WHERE status = 'active' AND next_run_at IS NULL AND json_extract(schedule, '$.kind') = 'once'"
)

# No code reads the reply-register policy key (``response_locale_policy``), so it is removed
# from every agent that holds one; an agent left with no parameters stores NULL, as every save writes it. A row whose
# ``engine_params`` is NULL, is not valid JSON or has no such key is left alone, and a second pass finds nothing to change.
STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL = (
    "UPDATE agents SET engine_params = CASE "
    "WHEN json_remove(engine_params, '$.response_locale_policy') = '{}' THEN NULL "
    "ELSE json_remove(engine_params, '$.response_locale_policy') END "
    "WHERE CASE WHEN json_valid(engine_params) "
    "THEN json_type(engine_params, '$.response_locale_policy') IS NOT NULL ELSE 0 END"
)

# A rollback snapshot holds the agent's parameters too; without this a rollback would write the retired key back into a
# live agent. The edit history is a read-only record and keeps what each version held.
STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL = (
    "UPDATE agent_profile_snapshots "
    "SET snapshot_data = json_remove(snapshot_data, '$.engine_params.response_locale_policy') "
    "WHERE CASE WHEN json_valid(snapshot_data) "
    "THEN json_type(snapshot_data, '$.engine_params.response_locale_policy') IS NOT NULL ELSE 0 END"
)
