"""Unit tests for Hermes cron migration converter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration.hermes_cron_converter import (
    build_hermes_cron_migration_plan,
    convert_hermes_job,
    load_hermes_cron_jobs,
)
from app.services.migration.source_payload_loader import build_coverage_items, load_source_payload
from myrm_agent_harness.toolkits.cron.types import ScheduleKind


def test_convert_hermes_cron_job_maps_schedule() -> None:
    job = {
        "id": "abc123",
        "name": "Morning brief",
        "prompt": "Summarize overnight news.",
        "schedule": {"kind": "cron", "expr": "0 9 * * *", "tz": "UTC"},
        "repeat": {"times": None, "completed": 0},
    }
    spec, skipped = convert_hermes_job(job)
    assert skipped is None
    assert spec is not None
    assert spec.name == "Morning brief"
    assert spec.schedule_kind == ScheduleKind.CRON
    assert spec.schedule_expr == "0 9 * * *"
    assert "model" not in spec.to_metadata_dict()


def test_convert_hermes_job_ignores_source_model_field() -> None:
    job = {
        "id": "model1",
        "name": "With model",
        "prompt": "Run task",
        "model": "hermes/main",
        "schedule": {"kind": "cron", "expr": "0 10 * * *"},
    }
    spec, skipped = convert_hermes_job(job)
    assert skipped is None
    assert spec is not None
    assert "model" not in spec.to_metadata_dict()


def test_convert_hermes_job_skips_no_agent_script() -> None:
    job = {
        "id": "script1",
        "name": "Watchdog",
        "no_agent": True,
        "script": "/tmp/check.sh",
        "schedule": {"kind": "interval", "minutes": 30},
    }
    spec, skipped = convert_hermes_job(job)
    assert spec is None
    assert skipped is not None
    assert skipped.reason == "no_agent_script"


def test_cron_skipped_preview_rows() -> None:
    from app.services.migration.hermes_cron_converter import (
        HermesCronMigrationPlan,
        HermesCronSkippedJob,
        cron_skipped_preview_rows,
    )

    plan = HermesCronMigrationPlan(
        importable=(),
        skipped=(HermesCronSkippedJob("id1", "Watchdog", "no_agent_script"),),
    )
    rows = cron_skipped_preview_rows(plan)
    assert rows == [{"source_hermes_id": "id1", "name": "Watchdog", "reason": "no_agent_script"}]


@pytest.fixture()
def hermes_jobs_file(tmp_path: Path) -> Path:
    jobs = [
        {
            "id": "job1",
            "name": "Daily",
            "prompt": "Run daily summary",
            "schedule": {"kind": "cron", "expr": "0 8 * * *"},
        }
    ]
    cron_dir = tmp_path / "cron"
    cron_dir.mkdir()
    path = cron_dir / "jobs.json"
    path.write_text(json.dumps(jobs), encoding="utf-8")
    return path


def test_load_hermes_cron_jobs_from_root(hermes_jobs_file: Path, tmp_path: Path) -> None:
    jobs = load_hermes_cron_jobs(tmp_path, [str(hermes_jobs_file)])
    assert len(jobs) == 1
    plan = build_hermes_cron_migration_plan(jobs)
    assert plan.importable_count == 1


def test_hermes_loader_includes_cron_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.migration.source_payload_loader.is_local_mode",
        lambda: True,
    )
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / "SOUL.md").write_text("Be helpful.", encoding="utf-8")
    (root / "config.yaml").write_text("model:\n  default: gpt-4\n", encoding="utf-8")
    cron_dir = root / "cron"
    cron_dir.mkdir()
    (cron_dir / "jobs.json").write_text(
        json.dumps(
            [
                {
                    "id": "j1",
                    "name": "Brief",
                    "prompt": "Brief me",
                    "schedule": {"kind": "once", "run_at": "2030-01-01T09:00:00+00:00"},
                }
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_source_payload({"competitor": "hermes", "root": str(root), "files": []})
    assert isinstance(loaded.get("hermes_cron_plan"), dict)
    coverage = build_coverage_items(loaded)
    labels = {row["label"] for row in coverage}
    assert "cron_lane" in labels
    assert "kanban_not_migrated" in labels


def test_build_import_readiness_emits_hermes_gate_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.memory.operations.crud.import_readiness import build_import_readiness

    monkeypatch.setattr(
        "app.services.memory.operations.crud.import_readiness._migration_feature_enabled",
        lambda _feature_id: False,
    )

    readiness = build_import_readiness(
        providers_configured=True,
        source_has_api_keys=False,
        diagnostic_status="ready",
        diagnostic_failed_count=0,
        mcp_config_count=0,
        workspace_rules_skipped=0,
        migration_competitor="hermes",
    )
    codes = {issue.code for issue in readiness.issues}
    assert "voice_feature_disabled" in codes
    assert "consensus_feature_disabled" in codes
