"""Agent Responsibility-Unit Governance — read-only inspection + guided merge.

[INPUT]
- AgentProfile list (AgentService.get_agent_list)
- Chat (90d usage), CronJobModel (bindings), UserConfig *Topics (channel bindings)
- AgentProfileSnapshot / rollback endpoints (undo for merge)

[OUTPUT]
- GET /governance/overview — orphan candidates + overlap pairs + per-agent asset rows
- POST /governance/merge/dry-run — field-level diff + affected bindings
- POST /governance/merge/execute — snapshot target, move config, rebind cron/channel,
  delete source via AgentService.delete_agent (existing cascade clears leftovers)

[POS]
Server business layer only (single-user; owner_label defaults to self on local).
Deterministic, zero LLM calls. Harness untouched: no toolkit/meta-tool changes,
no prompt changes (governance fields never enter the system prompt).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from myrm_agent_harness.backends.profiles.types import AgentProfile
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents._agent_response import _metadata_as_mapping
from app.core.channel_bridge.topic_config import _CHANNEL_LEVEL_KEY
from app.core.utils.errors import not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db, get_session
from app.database.dto import AgentUpdate
from app.database.models import Chat, UserConfig
from app.database.models.cron import CronJobModel
from app.services.agent.agent_service import AgentService
from app.services.agent.profile.profile_snapshot_service import ProfileSnapshotService

router = APIRouter()
logger = logging.getLogger(__name__)

_ORPHAN_IDLE_DAYS = 90
_OVERLAP_MIN_SHARED_SKILLS = 2
_GOVERNANCE_LIST_THRESHOLD = 3
_PROFILE_PAGE_SIZE = 200


async def _list_all_profiles() -> tuple[list[AgentProfile], int]:
    """Page through the full agent list (no 500-row truncation)."""
    profiles: list[AgentProfile] = []
    total = 0
    page = 1
    while True:
        batch, total = await AgentService.get_agent_list(page=page, page_size=_PROFILE_PAGE_SIZE)
        profiles.extend(batch)
        if len(profiles) >= total or not batch:
            break
        page += 1
    return profiles, total


class MergeDryRunRequest(BaseModel):
    source_id: str = Field(..., description="被合并（归档删除）的 Agent ID")
    target_id: str = Field(..., description="保留并继承配置的 Agent ID")


class MergeExecuteRequest(MergeDryRunRequest):
    confirm_name: str = Field(..., description="二次确认：目标 Agent 的准确名称")
    move_skills: bool = Field(True, description="是否把来源独有技能并入目标")
    move_subagents: bool = Field(True, description="是否把来源子智能体绑定并入目标")
    move_bindings: bool = Field(True, description="是否把定时/渠道绑定迁移到目标")


def _meta_str_list_value(meta: dict[str, Any], key: str) -> list[str]:
    """Read an optional string-list metadata field (tolerates missing/foreign shapes)."""
    raw = meta.get(key)
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None]
    return []


def _profile_asset(profile: AgentProfile) -> dict[str, Any]:
    """Extract governance-relevant asset fields from an AgentProfile."""
    meta = _metadata_as_mapping(profile)
    raw_skills = profile.skills or []
    raw_tools = profile.tools_allowed
    responsibility = meta.get("responsibility_scope")
    owner = meta.get("owner_label")
    return {
        "id": profile.id,
        "name": profile.display_name or profile.id,
        "built_in": bool(profile.built_in),
        "agent_type": str(meta.get("agent_type", "individual") or "individual"),
        "skill_ids": [str(s) for s in raw_skills],
        "tools": sorted(str(t) for t in raw_tools) if raw_tools else [],
        "subagent_ids": [s for s in _meta_str_list_value(meta, "subagent_ids") if s],
        "responsibility_scope": responsibility if isinstance(responsibility, str) else None,
        "owner_label": owner if isinstance(owner, str) else None,
        "acceptance_criteria": _meta_str_list_value(meta, "acceptance_criteria"),
    }


_BINDING_PREVIEW_LIMIT = 20


async def _channel_topics_by_agent() -> dict[str, list[str]]:
    """Map agent IDs to their bound channel topic IDs (single UserConfig query)."""
    mapping: dict[str, list[str]] = {}
    try:
        async with get_session() as session:
            result = await session.execute(select(UserConfig).where(UserConfig.config_key.like("%Topics")))
            for row in result.scalars().all():
                config = cast("dict[str, Any]", row.config_value)
                if not isinstance(config, dict):
                    continue
                for chat_id, group_topics in config.items():
                    if not isinstance(group_topics, dict):
                        continue
                    for thread_id, topic_cfg in group_topics.items():
                        if not isinstance(topic_cfg, dict) or not topic_cfg.get("agentId"):
                            continue
                        aid = str(topic_cfg["agentId"])
                        if str(chat_id) == "__global__":
                            topic_id = "global"
                        elif thread_id != _CHANNEL_LEVEL_KEY:
                            topic_id = f"{chat_id}:{thread_id}"
                        else:
                            topic_id = str(chat_id)
                        mapping.setdefault(aid, []).append(topic_id)
    except Exception as e:
        logger.warning("Governance channel-binding scan failed: %s", e)
    return mapping


async def _channel_bound_agent_ids() -> set[str]:
    """Collect agent IDs bound in any channel topic config (single UserConfig query)."""
    return set(await _channel_topics_by_agent())


def _overlap_pairs(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic overlap detection: shared skills + shared tools."""
    pairs: list[dict[str, Any]] = []
    for i in range(len(assets)):
        for j in range(i + 1, len(assets)):
            a, b = assets[i], assets[j]
            shared_skills = sorted(set(a["skill_ids"]) & set(b["skill_ids"]))
            shared_tools = sorted(set(a["tools"]) & set(b["tools"]))
            if len(shared_skills) >= _OVERLAP_MIN_SHARED_SKILLS or (shared_skills and shared_tools):
                pairs.append(
                    {
                        "agent_a": {"id": a["id"], "name": a["name"]},
                        "agent_b": {"id": b["id"], "name": b["name"]},
                        "shared_skills": shared_skills,
                        "shared_tools": shared_tools,
                    }
                )
    return pairs


@router.get("/governance/overview")
async def governance_overview(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Read-only responsibility-unit inspection: usage, bindings, orphans, overlaps."""
    profiles, total = await _list_all_profiles()
    assets = [_profile_asset(p) for p in profiles]

    since = datetime.now(UTC) - timedelta(days=_ORPHAN_IDLE_DAYS)
    usage_rows = (
        await db.execute(
            select(
                Chat.agent_id,
                func.count(Chat.id).label("sessions"),
                func.max(Chat.created_at).label("last_used"),
            )
            .where(and_(Chat.created_at >= since, Chat.deleted_at.is_(None)))
            .group_by(Chat.agent_id)
        )
    ).all()
    usage = {str(r.agent_id or "default"): {"sessions": int(r.sessions), "last_used": r.last_used} for r in usage_rows}

    cron_rows = (
        await db.execute(
            select(CronJobModel.agent_id, func.count(CronJobModel.id))
            .where(CronJobModel.status == "active")
            .group_by(CronJobModel.agent_id)
        )
    ).all()
    cron_counts = {str(r[0]): int(r[1]) for r in cron_rows if r[0]}

    channel_bound = await _channel_bound_agent_ids()

    team_members: set[str] = set()
    for a in assets:
        team_members.update(a["subagent_ids"])

    orphans: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for a in assets:
        aid = a["id"]
        u = usage.get(aid, {"sessions": 0, "last_used": None})
        cron_n = cron_counts.get(aid, 0)
        bound = aid in channel_bound
        in_team = aid in team_members
        row = {
            **a,
            "sessions_90d": u["sessions"],
            "last_used": u["last_used"].isoformat() if u["last_used"] else None,
            "active_crons": cron_n,
            "channel_bound": bound,
            "team_member": in_team,
        }
        rows.append(row)
        if not a["built_in"] and u["sessions"] == 0 and cron_n == 0 and not bound and not in_team:
            orphans.append({"id": aid, "name": a["name"], "reason": "90天零会话且无定时/渠道/团队绑定"})

    overlaps = _overlap_pairs(assets)
    return success_response(
        data={
            "total": total,
            "needs_attention": (len(orphans) + len(overlaps) > 0) and total >= _GOVERNANCE_LIST_THRESHOLD,
            "agents": rows,
            "orphans": orphans,
            "overlaps": overlaps,
        }
    )


def _merge_plan(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Pure field-level merge plan (unit-testable, no I/O)."""
    move_skills = sorted(set(source["skill_ids"]) - set(target["skill_ids"]))
    move_subagents = sorted(set(source["subagent_ids"]) - set(target["subagent_ids"]))
    conflicts: list[str] = []
    if source.get("responsibility_scope") and target.get("responsibility_scope"):
        conflicts.append("双方均已填写职责定义，需人工二选一（默认保留目标）")
    return {
        "move_skills": move_skills,
        "move_subagents": move_subagents,
        "keep_tools_note": "内置工具取并集（执行时合并）",
        "conflicts": conflicts,
    }


@router.post("/governance/merge/dry-run")
async def merge_dry_run(body: MergeDryRunRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Preview a merge: field diff + affected bindings. No writes."""
    if body.source_id == body.target_id:
        return success_response(data={"ok": False, "reason": "来源与目标不能是同一智能体"})
    profiles, _ = await _list_all_profiles()
    by_id = {p.id: _profile_asset(p) for p in profiles}
    source, target = by_id.get(body.source_id), by_id.get(body.target_id)
    if source is None or target is None:
        raise not_found_error("Agent")
    if source["built_in"]:
        return success_response(data={"ok": False, "reason": "内置智能体不可被合并归档"})
    if target["built_in"]:
        return success_response(data={"ok": False, "reason": "不可并入内置智能体（保护系统资产）"})
    cron_names = (
        (
            await db.execute(
                select(CronJobModel.name).where(CronJobModel.agent_id == body.source_id).limit(_BINDING_PREVIEW_LIMIT + 1)
            )
        )
        .scalars()
        .all()
    )
    cron_count = (
        await db.execute(select(func.count(CronJobModel.id)).where(CronJobModel.agent_id == body.source_id))
    ).scalar() or 0
    channel_topics = (await _channel_topics_by_agent()).get(body.source_id, [])
    return success_response(
        data={
            "ok": True,
            "source": {"id": source["id"], "name": source["name"]},
            "target": {"id": target["id"], "name": target["name"]},
            "plan": _merge_plan(source, target),
            "affected": {
                "cron_jobs": int(cron_count),
                "cron_names": [str(n) for n in cron_names[:_BINDING_PREVIEW_LIMIT]],
                "cron_truncated": len(cron_names) > _BINDING_PREVIEW_LIMIT,
                "channel_bound": len(channel_topics) > 0,
                "channel_topics": channel_topics[:_BINDING_PREVIEW_LIMIT],
                "channel_truncated": len(channel_topics) > _BINDING_PREVIEW_LIMIT,
                "kanban_note": "看板任务引用将被现有删除级联清空，需在看板手动重指派",
            },
        }
    )


@router.post("/governance/merge/execute")
async def merge_execute(body: MergeExecuteRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Execute a merge: snapshot target, move config, rebind, delete source."""
    profiles, _ = await _list_all_profiles()
    by_id = {p.id: p for p in profiles}
    source, target = by_id.get(body.source_id), by_id.get(body.target_id)
    if source is None or target is None:
        raise not_found_error("Agent")
    target_name = target.display_name or target.id
    if body.confirm_name.strip() != target_name.strip():
        return success_response(data={"ok": False, "reason": "二次确认名称与目标不一致，拒绝执行"})
    if source.built_in:
        return success_response(data={"ok": False, "reason": "内置智能体不可被合并归档"})
    if target.built_in:
        return success_response(data={"ok": False, "reason": "不可并入内置智能体（保护系统资产）"})

    src_asset = _profile_asset(source)
    tgt_asset = _profile_asset(target)
    steps: list[dict[str, Any]] = []

    snapshot_id = await ProfileSnapshotService.save_profile_snapshot(target.id, reason="governance-merge")
    steps.append({"step": "snapshot_target", "ok": snapshot_id is not None, "snapshot_id": snapshot_id})

    merged_skills = sorted(set(tgt_asset["skill_ids"]) | (set(src_asset["skill_ids"]) if body.move_skills else set()))
    merged_subagents = sorted(set(tgt_asset["subagent_ids"]) | (set(src_asset["subagent_ids"]) if body.move_subagents else set()))
    merged_tools = sorted(set(tgt_asset["tools"]) | set(src_asset["tools"]))
    outcome = await AgentService.update_agent(
        target.id,
        AgentUpdate(skill_ids=merged_skills, subagent_ids=merged_subagents, enabled_builtin_tools=merged_tools or None),
    )
    steps.append({"step": "update_target", "ok": outcome is not None})
    if outcome is None:
        return success_response(
            data={
                "ok": False,
                "reason": "目标更新失败，已中止（来源未动，可用快照回滚目标）",
                "steps": steps,
                "undo": {"rollback": f"/{target.id}/rollback"},
            }
        )

    if body.move_bindings:
        cron_count = (
            await db.execute(select(func.count()).select_from(CronJobModel).where(CronJobModel.agent_id == source.id))
        ).scalar() or 0
        await db.execute(sql_update(CronJobModel).where(CronJobModel.agent_id == source.id).values(agent_id=target.id))
        await db.commit()
        steps.append({"step": "rebind_cron", "ok": True, "count": int(cron_count)})
        try:
            from sqlalchemy.orm.attributes import flag_modified

            async with get_session() as session:
                result = await session.execute(select(UserConfig).where(UserConfig.config_key.like("%Topics")))
                moved = 0
                for row in result.scalars().all():
                    channel_config = cast("dict[str, Any]", row.config_value)
                    if not isinstance(channel_config, dict):
                        continue
                    changed = False
                    for group_topics in channel_config.values():
                        if not isinstance(group_topics, dict):
                            continue
                        for topic_cfg in group_topics.values():
                            if isinstance(topic_cfg, dict) and topic_cfg.get("agentId") == source.id:
                                topic_cfg["agentId"] = target.id
                                changed = True
                                moved += 1
                    if changed:
                        flag_modified(row, "config_value")
                await session.commit()
            steps.append({"step": "rebind_channel", "ok": True, "count": moved})
        except Exception as e:
            logger.error("Governance merge channel rebind failed: %s", e)
            steps.append({"step": "rebind_channel", "ok": False, "reason": str(e)})

    deleted = await AgentService.delete_agent(source.id)
    steps.append({"step": "delete_source", "ok": bool(deleted)})

    ok = all(s.get("ok", False) for s in steps)
    return success_response(data={"ok": ok, "steps": steps, "undo": {"rollback": f"/{target.id}/rollback"}})
