"""Lifecycle schedulers.

[INPUT]
- app.services / app.core schedulers (POS: started schedulers)

[OUTPUT]
- Every start_*/stop_* hook and the job functions, re-exported for the lifespan.

[POS]
Aggregate exit of the scheduler package: cron, context, maintenance, security, kanban and backup.
"""

from __future__ import annotations

from .backup import (
    _remote_backup_auto_sync_job,
    start_remote_backup_scheduler,
    stop_remote_backup_scheduler,
)
from .context import (
    _context_cleanup_job,
    start_context_cleanup_scheduler,
    start_context_compaction_telemetry_dispatcher,
    start_memory_brief_status_telemetry_dispatcher,
    start_memory_guardian_guard_telemetry_dispatcher,
    stop_context_cleanup_scheduler,
    stop_context_compaction_telemetry_dispatcher,
    stop_memory_brief_status_telemetry_dispatcher,
    stop_memory_guardian_guard_telemetry_dispatcher,
)
from .cron import (
    start_cron_scheduler,
)
from .kanban import (
    start_kanban_dispatchers,
    stop_kanban_dispatchers,
)
from .maintenance import (
    _checkpoint_history_prune_job,
    _db_maintenance_job,
    _incognito_cleanup_job,
    _instance_auto_backup_job,
    start_db_maintenance_scheduler,
    stop_db_maintenance_scheduler,
)
from .security import (
    _approval_ttl_job,
    _auth_log_cleanup_job,
    _cancellation_token_cleanup_job,
    _login_session_cleanup_job,
    start_approval_ttl_scheduler,
    start_auth_log_cleanup_scheduler,
    start_cancellation_cleanup_scheduler,
    start_login_session_cleanup_scheduler,
    stop_approval_ttl_scheduler,
    stop_auth_log_cleanup_scheduler,
    stop_cancellation_cleanup_scheduler,
    stop_login_session_cleanup_scheduler,
)

__all__ = [
    "_context_cleanup_job",
    "_db_maintenance_job",
    "_incognito_cleanup_job",
    "_checkpoint_history_prune_job",
    "_instance_auto_backup_job",
    "_approval_ttl_job",
    "_cancellation_token_cleanup_job",
    "_login_session_cleanup_job",
    "_auth_log_cleanup_job",
    "_remote_backup_auto_sync_job",
    "logger",
    "start_cron_scheduler",
    "start_context_cleanup_scheduler",
    "stop_context_cleanup_scheduler",
    "start_context_compaction_telemetry_dispatcher",
    "stop_context_compaction_telemetry_dispatcher",
    "start_memory_brief_status_telemetry_dispatcher",
    "stop_memory_brief_status_telemetry_dispatcher",
    "start_memory_guardian_guard_telemetry_dispatcher",
    "stop_memory_guardian_guard_telemetry_dispatcher",
    "start_db_maintenance_scheduler",
    "stop_db_maintenance_scheduler",
    "start_approval_ttl_scheduler",
    "stop_approval_ttl_scheduler",
    "start_cancellation_cleanup_scheduler",
    "stop_cancellation_cleanup_scheduler",
    "start_login_session_cleanup_scheduler",
    "stop_login_session_cleanup_scheduler",
    "start_auth_log_cleanup_scheduler",
    "stop_auth_log_cleanup_scheduler",
    "start_kanban_dispatchers",
    "stop_kanban_dispatchers",
    "start_remote_backup_scheduler",
    "stop_remote_backup_scheduler",
]
