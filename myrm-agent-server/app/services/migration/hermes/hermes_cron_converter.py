"""Hermes cron/jobs.json → Myrm cron migration converter.

[INPUT]
Raw Hermes job dicts from ~/.hermes/cron/jobs.json (and per-profile stores).

[OUTPUT]
HermesCronMigrationJobSpec / HermesCronMigrationPlan for wizard preview + confirm.
Skipped preview rows for dry-run API (`cron_skipped_preview_rows`).

[POS]
Server migration lane — pure conversion + plan assembly; apply lives in hermes_cron_migration.py.
Migrated cron jobs omit model (bound agent profile is model SSOT).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from myrm_agent_harness.toolkits.cron.types import JobType, Schedule, ScheduleKind

from app.core.cron.adapters.injection_scan import scan_cron_prompt

logger = logging.getLogger(__name__)

HermesCronSkipReason = Literal[
    "no_agent_script",
    "missing_prompt",
    "invalid_schedule",
    "prompt_injection",
    "unsupported_job_type",
]


@dataclass(frozen=True, slots=True)
class HermesCronMigrationJobSpec:
    """Serializable cron job spec for migration confirm."""

    name: str
    job_type: JobType
    schedule_kind: ScheduleKind
    schedule_expr: str | None = None
    schedule_tz: str | None = None
    schedule_interval_ms: int | None = None
    schedule_run_at: str | None = None
    prompt: str | None = None
    max_fires: int | None = None
    source_hermes_id: str = ""
    source_profile: str | None = None

    def to_metadata_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "job_type": self.job_type.value,
            "schedule_kind": self.schedule_kind.value,
            "schedule_expr": self.schedule_expr,
            "schedule_tz": self.schedule_tz,
            "schedule_interval_ms": self.schedule_interval_ms,
            "schedule_run_at": self.schedule_run_at,
            "prompt": self.prompt,
            "max_fires": self.max_fires,
            "source_hermes_id": self.source_hermes_id,
            "source_profile": self.source_profile,
        }

    @classmethod
    def from_metadata_dict(cls, raw: dict[str, object]) -> HermesCronMigrationJobSpec | None:
        name = str(raw.get("name", "")).strip()
        if not name:
            return None
        job_type_raw = str(raw.get("job_type", JobType.AGENT.value))
        schedule_kind_raw = str(raw.get("schedule_kind", ""))
        try:
            job_type = JobType(job_type_raw)
            schedule_kind = ScheduleKind(schedule_kind_raw)
        except ValueError:
            return None
        max_fires_raw = raw.get("max_fires")
        max_fires = int(max_fires_raw) if isinstance(max_fires_raw, int) else None
        return cls(
            name=name,
            job_type=job_type,
            schedule_kind=schedule_kind,
            schedule_expr=str(raw["schedule_expr"]) if isinstance(raw.get("schedule_expr"), str) else None,
            schedule_tz=str(raw["schedule_tz"]) if isinstance(raw.get("schedule_tz"), str) else None,
            schedule_interval_ms=(int(raw["schedule_interval_ms"]) if isinstance(raw.get("schedule_interval_ms"), int) else None),
            schedule_run_at=str(raw["schedule_run_at"]) if isinstance(raw.get("schedule_run_at"), str) else None,
            prompt=str(raw["prompt"]) if isinstance(raw.get("prompt"), str) else None,
            max_fires=max_fires,
            source_hermes_id=str(raw.get("source_hermes_id", "")),
            source_profile=str(raw["source_profile"]) if isinstance(raw.get("source_profile"), str) else None,
        )

    def to_schedule(self) -> Schedule:
        if self.schedule_kind == ScheduleKind.CRON:
            return Schedule(
                kind=ScheduleKind.CRON,
                expr=self.schedule_expr,
                tz=self.schedule_tz,
            )
        if self.schedule_kind == ScheduleKind.INTERVAL:
            return Schedule(
                kind=ScheduleKind.INTERVAL,
                interval_ms=self.schedule_interval_ms,
            )
        run_at = datetime.fromisoformat(self.schedule_run_at) if self.schedule_run_at else None
        if run_at is not None and run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)
        return Schedule(kind=ScheduleKind.ONCE, run_at=run_at)


@dataclass(frozen=True, slots=True)
class HermesCronSkippedJob:
    source_hermes_id: str
    name: str
    reason: HermesCronSkipReason

    def to_metadata_dict(self) -> dict[str, str]:
        return {
            "source_hermes_id": self.source_hermes_id,
            "name": self.name,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class HermesCronMigrationPlan:
    importable: tuple[HermesCronMigrationJobSpec, ...]
    skipped: tuple[HermesCronSkippedJob, ...] = field(default_factory=tuple)

    @property
    def importable_count(self) -> int:
        return len(self.importable)

    def to_metadata_dict(self) -> dict[str, object]:
        return {
            "importable": [item.to_metadata_dict() for item in self.importable],
            "skipped": [item.to_metadata_dict() for item in self.skipped],
        }

    @classmethod
    def from_metadata_dict(cls, raw: dict[str, object]) -> HermesCronMigrationPlan:
        importable: list[HermesCronMigrationJobSpec] = []
        skipped: list[HermesCronSkippedJob] = []
        importable_raw = raw.get("importable")
        if isinstance(importable_raw, list):
            for item in importable_raw:
                if isinstance(item, dict):
                    spec = HermesCronMigrationJobSpec.from_metadata_dict(item)
                    if spec is not None:
                        importable.append(spec)
        skipped_raw = raw.get("skipped")
        if isinstance(skipped_raw, list):
            for item in skipped_raw:
                if isinstance(item, dict):
                    reason = str(item.get("reason", "unsupported_job_type"))
                    if reason not in {
                        "no_agent_script",
                        "missing_prompt",
                        "invalid_schedule",
                        "prompt_injection",
                        "unsupported_job_type",
                    }:
                        reason = "unsupported_job_type"
                    skipped.append(
                        HermesCronSkippedJob(
                            source_hermes_id=str(item.get("source_hermes_id", "")),
                            name=str(item.get("name", "")),
                            reason=reason,  # type: ignore[arg-type]
                        ),
                    )
        return cls(importable=tuple(importable), skipped=tuple(skipped))


def discover_hermes_cron_job_files(root: Path) -> list[tuple[Path, str | None]]:
    """Return (jobs.json path, profile slug or None) under a Hermes home root."""

    found: list[tuple[Path, str | None]] = []
    primary = root / "cron" / "jobs.json"
    if primary.is_file():
        found.append((primary, None))

    profiles_dir = root / "profiles"
    if profiles_dir.is_dir():
        for profile_dir in sorted(profiles_dir.iterdir()):
            if not profile_dir.is_dir():
                continue
            profile_jobs = profile_dir / "cron" / "jobs.json"
            if profile_jobs.is_file():
                found.append((profile_jobs, profile_dir.name))
    return found


def read_hermes_jobs_file(path: Path) -> list[dict[str, object]]:
    """Load Hermes cron jobs list from jobs.json (dict wrapper or bare list)."""

    try:
        content = path.read_text(encoding="utf-8-sig")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read Hermes cron jobs from %s: %s", path, exc)
        return []

    if isinstance(data, dict):
        jobs_raw = data.get("jobs")
        if isinstance(jobs_raw, list):
            return [item for item in jobs_raw if isinstance(item, dict)]
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def load_hermes_cron_jobs(root: Path, file_paths: list[str]) -> list[dict[str, object]]:
    """Collect raw Hermes cron job records from probe paths and default locations."""

    collected: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    def ingest(path: Path, profile: str | None) -> None:
        for job in read_hermes_jobs_file(path):
            job_id = str(job.get("id", "")).strip()
            dedupe_key = f"{profile or ''}:{job_id or job.get('name', '')}"
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            enriched = dict(job)
            if profile:
                enriched["_migration_profile"] = profile
            enriched["_migration_source_path"] = str(path)
            collected.append(enriched)

    for raw_path in file_paths:
        path = Path(raw_path)
        if not path.is_file():
            continue
        if path.name != "jobs.json" or "cron" not in path.parts:
            continue
        profile: str | None = None
        parts = path.parts
        if "profiles" in parts:
            idx = parts.index("profiles")
            if idx + 1 < len(parts):
                profile = parts[idx + 1]
        ingest(path, profile)

    for path, profile in discover_hermes_cron_job_files(root):
        if str(path) in file_paths:
            continue
        ingest(path, profile)

    return collected


def _map_hermes_schedule(schedule_raw: object) -> Schedule | None:
    if not isinstance(schedule_raw, dict):
        return None
    kind = str(schedule_raw.get("kind", "")).strip().lower()
    if kind == "cron":
        expr = schedule_raw.get("expr")
        if not isinstance(expr, str) or not expr.strip():
            return None
        tz_raw = schedule_raw.get("tz")
        tz = tz_raw.strip() if isinstance(tz_raw, str) and tz_raw.strip() else None
        return Schedule(kind=ScheduleKind.CRON, expr=expr.strip(), tz=tz)
    if kind == "interval":
        minutes_raw = schedule_raw.get("minutes")
        if not isinstance(minutes_raw, (int, float)) or minutes_raw <= 0:
            return None
        interval_ms = max(100, int(float(minutes_raw) * 60 * 1000))
        return Schedule(kind=ScheduleKind.INTERVAL, interval_ms=interval_ms)
    if kind == "once":
        run_at_raw = schedule_raw.get("run_at")
        if not isinstance(run_at_raw, str) or not run_at_raw.strip():
            return None
        try:
            run_at = datetime.fromisoformat(run_at_raw.strip())
        except ValueError:
            return None
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)
        return Schedule(kind=ScheduleKind.ONCE, run_at=run_at)
    return None


def _extract_max_fires(repeat_raw: object) -> int | None:
    if not isinstance(repeat_raw, dict):
        return None
    times = repeat_raw.get("times")
    if isinstance(times, int) and times > 0:
        return times
    return None


def convert_hermes_job(job: dict[str, object]) -> tuple[HermesCronMigrationJobSpec | None, HermesCronSkippedJob | None]:
    source_id = str(job.get("id", "")).strip()
    name = str(job.get("name", "")).strip() or source_id or "Hermes cron job"
    profile_raw = job.get("_migration_profile")
    profile = profile_raw.strip() if isinstance(profile_raw, str) and profile_raw.strip() else None

    if job.get("no_agent") is True:
        return None, HermesCronSkippedJob(source_id, name, "no_agent_script")

    prompt_raw = job.get("prompt")
    prompt = prompt_raw.strip() if isinstance(prompt_raw, str) and prompt_raw.strip() else None
    if not prompt:
        return None, HermesCronSkippedJob(source_id, name, "missing_prompt")

    injection_findings = scan_cron_prompt(prompt)
    if injection_findings:
        return None, HermesCronSkippedJob(source_id, name, "prompt_injection")

    schedule = _map_hermes_schedule(job.get("schedule"))
    if schedule is None:
        return None, HermesCronSkippedJob(source_id, name, "invalid_schedule")

    max_fires = _extract_max_fires(job.get("repeat"))

    run_at_iso = schedule.run_at.isoformat() if schedule.kind == ScheduleKind.ONCE and schedule.run_at else None

    spec = HermesCronMigrationJobSpec(
        name=name[:200],
        job_type=JobType.AGENT,
        schedule_kind=schedule.kind,
        schedule_expr=schedule.expr,
        schedule_tz=schedule.tz,
        schedule_interval_ms=schedule.interval_ms,
        schedule_run_at=run_at_iso,
        prompt=prompt,
        max_fires=max_fires,
        source_hermes_id=source_id,
        source_profile=profile,
    )
    return spec, None


def build_hermes_cron_migration_plan(jobs: list[dict[str, object]]) -> HermesCronMigrationPlan:
    importable: list[HermesCronMigrationJobSpec] = []
    skipped: list[HermesCronSkippedJob] = []
    for job in jobs:
        spec, skip = convert_hermes_job(job)
        if spec is not None:
            importable.append(spec)
        elif skip is not None:
            skipped.append(skip)
    return HermesCronMigrationPlan(importable=tuple(importable), skipped=tuple(skipped))


def cron_skipped_preview_rows(plan: HermesCronMigrationPlan) -> list[dict[str, str]]:
    """Serialize skipped cron jobs for dry-run API preview."""

    return [item.to_metadata_dict() for item in plan.skipped]
