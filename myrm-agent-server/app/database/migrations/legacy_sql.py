"""兼容性清理 SQL。

[POS]
数据库迁移包里独立的一次性回填/清理语句。
"""

from __future__ import annotations

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

# 数据库迁移语句（按顺序执行）
