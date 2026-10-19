"""Preview rows assembled for the import dry-run review.

[INPUT]
app.services.migration.source.source_migration_types (POS: 迁移车道与指令计划)

[OUTPUT]
build_lane_rows / build_session_preview / build_instruction_preview /
build_token_economics / skipped_cron_preview: the content-safe rows the wizard
renders, each derived from the reviewed session metadata.

[POS]
Presentation half of the dry-run: pure functions over already-loaded facts, so the
handler stays a sequence of decisions instead of nested comprehensions.
"""

from __future__ import annotations

from app.schemas.memory.archive import (
    CronMigrationSkippedPreviewItem,
    MigrationLanePreviewItem,
    TokenEconomicsComparison,
)
from app.services.memory.operations.crud.import_dry_run_source import (
    LoadedSource,
    SideChannels,
)
from app.services.migration.source.source_migration_types import (
    MigrationLanePreview,
    build_lane_previews,
)

_COMPETITOR_AVG_SKILL_TOKENS = 500
_MYRM_AVG_INDEX_TOKENS = 30


def skipped_cron_preview(raw: dict[str, object] | None) -> list[CronMigrationSkippedPreviewItem]:
    """Name + reason rows for cron jobs the converter refused to import."""

    if not isinstance(raw, dict):
        return []
    from app.services.migration.hermes.hermes_cron_converter import (
        HermesCronMigrationPlan,
        cron_skipped_preview_rows,
    )

    plan = HermesCronMigrationPlan.from_metadata_dict(raw)
    return [
        CronMigrationSkippedPreviewItem(name=str(row["name"]), reason=str(row["reason"]))
        for row in cron_skipped_preview_rows(plan)
        if row.get("name") and row.get("reason")
    ]


def build_lane_rows(
    *,
    loaded: LoadedSource,
    channels: SideChannels,
    providers_configured: bool,
) -> list[MigrationLanePreview]:
    """Coverage rows for instruction / memory / skill / key lanes plus cron and sessions."""

    lanes = build_lane_previews(
        instruction=loaded.instruction_plan,
        memory_mapped=0,
        memory_status="pending",
        skill_count=loaded.pending_skills_total or len(loaded.pending_skills),
        has_api_keys=loaded.source_has_api_keys,
        providers_ready=providers_configured,
        include_episodic=loaded.migration_opts.include_episodic,
    )
    if loaded.competitor == "hermes":
        lanes = [*lanes, _cron_lane(channels.cron_plan_raw)]
    if channels.sessions:
        lanes.append(
            MigrationLanePreview(
                lane="session",
                status="ready",
                label="session_lane",
                detail=f"{len(channels.sessions)} session(s) ready for resumption",
            ),
        )
    return lanes


def _cron_lane(cron_plan_raw: dict[str, object] | None) -> MigrationLanePreview:
    importable_count = 0
    skipped_count = 0
    if isinstance(cron_plan_raw, dict):
        importable_raw = cron_plan_raw.get("importable")
        skipped_raw = cron_plan_raw.get("skipped")
        if isinstance(importable_raw, list):
            importable_count = len(importable_raw)
        if isinstance(skipped_raw, list):
            skipped_count = len(skipped_raw)

    if importable_count > 0:
        detail = f"{importable_count} scheduled task(s) will import paused" + (
            f"; {skipped_count} skipped" if skipped_count else ""
        )
        status = "ready"
    elif skipped_count > 0:
        detail = f"{skipped_count} cron job(s) detected but not importable"
        status = "warning"
    else:
        detail = "no cron jobs detected"
        status = "missing"
    return MigrationLanePreview(lane="cron", status=status, label="cron_lane", detail=detail)


def build_lane_response_rows(
    lanes: list[MigrationLanePreview],
    *,
    memory_status: str,
    memory_mapped: int,
    episodic_excluded: bool,
) -> list[MigrationLanePreviewItem]:
    """Project lane previews into the API rows, folding the real memory outcome in."""

    return [
        MigrationLanePreviewItem(
            lane=lane.lane,
            status=memory_status if lane.lane == "memory" else lane.status,
            label=lane.label,
            detail=(
                f"{memory_mapped} mapped item(s)" + (", episodic excluded" if episodic_excluded else "")
                if lane.lane == "memory"
                else lane.detail
            ),
        )
        for lane in lanes
    ]


def build_session_preview(sessions: list[dict[str, object]]) -> list[dict[str, object]]:
    """Bounded per-session rows: title, turn/tool counts and workspace hint."""

    return [
        {
            "session_id": str(session.get("session_id", "")),
            "title": str(session.get("title", "")),
            "turn_count": len(session.get("turns") or []),
            "tool_call_count": int(session.get("total_tool_calls") or 0),
            "source_platform": str(session.get("source_platform", "")),
            "workspace_hint": session.get("detected_workspace_hint"),
        }
        for session in sessions
    ]


def build_instruction_preview(
    instruction_plan: dict[str, object],
) -> tuple[str | None, list[str]]:
    """Persona excerpt plus rule filenames, never the rule bodies."""

    persona_raw = str(instruction_plan.get("agent_persona", "")).strip()
    persona = persona_raw[:1200] or None
    rule_names: list[str] = []
    rules_raw = instruction_plan.get("workspace_rules")
    if isinstance(rules_raw, list):
        for item in rules_raw:
            if isinstance(item, dict):
                name = str(item.get("filename", "")).strip()
                if name:
                    rule_names.append(name)
    return persona, rule_names


def build_token_economics(skill_count: int) -> TokenEconomicsComparison | None:
    """Per-turn cost of full skill injection versus on-demand indexing."""

    if skill_count <= 0:
        return None
    source_tokens = skill_count * _COMPETITOR_AVG_SKILL_TOKENS
    myrm_tokens = skill_count * _MYRM_AVG_INDEX_TOKENS
    return TokenEconomicsComparison(
        skill_count=skill_count,
        source_tokens_per_turn=source_tokens,
        myrm_tokens_per_turn=myrm_tokens,
        savings_percent=round((1 - myrm_tokens / source_tokens) * 100, 1) if source_tokens > 0 else 0.0,
    )
