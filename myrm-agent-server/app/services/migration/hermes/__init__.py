"""Hermes migration domain: cron jobs converter/apply/rollback.

[INPUT]
- Hermes ``jobs.json`` / cron job files discovered by the source probes.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``hermes`` subpackage:
  - hermes_cron_converter: jobs.json → Myrm CronJob mapping + dry-run plan +
    skipped preview rows
  - hermes_cron_migration: confirm 写入 CronManager（默认 paused）+ batch rollback

[POS]
Server business layer. Single Hermes migration domain: cron jobs are converted,
applied (paused by default) and rolled back in the Wizard confirm path. MoA
presets are intentionally not migrated.
"""

from app.services.migration.hermes.hermes_cron_converter import (
    HermesCronMigrationJobSpec,
    HermesCronMigrationPlan,
    HermesCronSkippedJob,
    build_hermes_cron_migration_plan,
    convert_hermes_job,
    cron_skipped_preview_rows,
    discover_hermes_cron_job_files,
    load_hermes_cron_jobs,
    read_hermes_jobs_file,
)
from app.services.migration.hermes.hermes_cron_migration import (
    HermesCronApplyResult,
    apply_hermes_cron_migration_plan,
    rollback_hermes_cron_migration,
)

__all__ = [
    "HermesCronApplyResult",
    "HermesCronMigrationJobSpec",
    "HermesCronMigrationPlan",
    "HermesCronSkippedJob",
    "apply_hermes_cron_migration_plan",
    "build_hermes_cron_migration_plan",
    "convert_hermes_job",
    "cron_skipped_preview_rows",
    "discover_hermes_cron_job_files",
    "load_hermes_cron_jobs",
    "read_hermes_jobs_file",
    "rollback_hermes_cron_migration",
]
