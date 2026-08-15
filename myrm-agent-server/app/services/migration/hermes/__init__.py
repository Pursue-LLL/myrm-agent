"""Hermes migration domain: cron jobs converter/apply/rollback + MoA overlay.

[INPUT]
- Hermes ``jobs.json`` / cron job files discovered by the source probes.
- Hermes ``config.json`` (moa.presets) + target Agent engine params.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``hermes`` subpackage:
  - hermes_cron_converter: jobs.json → Myrm CronJob mapping + dry-run plan +
    skipped preview rows
  - hermes_cron_migration: confirm 写入 CronManager（默认 paused）+ batch rollback
  - hermes_moa_migrator: Hermes ``moa.presets`` → 目标 Agent ``moa_overlay``
    (ref model + fanout/privacy params; aggregator not migrated)

[POS]
Server business layer. Single Hermes migration domain: cron and MoA migrate
alongside each other in the Wizard confirm path, so they stay co-located under
one facade.
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
from app.services.migration.hermes.hermes_moa_migrator import (
    MoaOverlayMigrationResult,
    agent_has_moa_overlay_refs,
    build_moa_overlay_from_hermes_config,
    extract_hermes_moa_block,
    hermes_config_has_moa,
    hermes_slot_to_myrm_selection,
    migrate_hermes_moa_overlay,
    resolve_hermes_moa_preset,
)

__all__ = [
    "HermesCronApplyResult",
    "HermesCronMigrationJobSpec",
    "HermesCronMigrationPlan",
    "HermesCronSkippedJob",
    "MoaOverlayMigrationResult",
    "agent_has_moa_overlay_refs",
    "apply_hermes_cron_migration_plan",
    "build_hermes_cron_migration_plan",
    "build_moa_overlay_from_hermes_config",
    "convert_hermes_job",
    "cron_skipped_preview_rows",
    "discover_hermes_cron_job_files",
    "extract_hermes_moa_block",
    "hermes_config_has_moa",
    "hermes_slot_to_myrm_selection",
    "load_hermes_cron_jobs",
    "migrate_hermes_moa_overlay",
    "read_hermes_jobs_file",
    "resolve_hermes_moa_preset",
    "rollback_hermes_cron_migration",
]
