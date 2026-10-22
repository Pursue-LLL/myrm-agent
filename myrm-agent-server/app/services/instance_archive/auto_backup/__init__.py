"""Scheduled whole-instance backup for local and desktop instances.

[INPUT]
- app.services.instance_archive.export_jobs::ExportJobManager (POS: background export jobs, one at a time, shared with the manual flow)
- app.services.instance_archive.auto_backup.service (POS: scheduled backup as the API and the scheduler use it)

[OUTPUT]
- AutoBackupService / AutoBackupView / get_auto_backup_service: the API-facing service
- run_auto_backup_tick: scheduler entry point
- AutoBackupSettings / AutoBackupState / BackupFile / Frequency / AutoBackupError: contracts
- ALERT_COMPONENT, KEEP_MIN / KEEP_MAX: values the API and UI agree on

[POS]
Off by default. When enabled it writes the same archive as "Create backup" (no keys,
no passphrase) to a folder the user chooses, keeps the newest N, and tells the user
when it keeps failing. See _ARCH.md.
"""

from app.services.instance_archive.auto_backup.models import (
    DEFAULT_KEEP,
    KEEP_MAX,
    KEEP_MIN,
    AutoBackupError,
    AutoBackupSettings,
    AutoBackupState,
    BackupFile,
    Frequency,
)
from app.services.instance_archive.auto_backup.service import (
    ALERT_COMPONENT,
    AutoBackupService,
    AutoBackupView,
    get_auto_backup_service,
    run_auto_backup_tick,
)

__all__ = [
    "ALERT_COMPONENT",
    "DEFAULT_KEEP",
    "KEEP_MAX",
    "KEEP_MIN",
    "AutoBackupError",
    "AutoBackupService",
    "AutoBackupSettings",
    "AutoBackupState",
    "AutoBackupView",
    "BackupFile",
    "Frequency",
    "get_auto_backup_service",
    "run_auto_backup_tick",
]
