"""Agent Profile Audit API — configuration exposure risk assessment.

[INPUT]
- Agent ID (path param)
- Database session for Agent profile lookup

[OUTPUT]
- ProfileAuditResult: score, risk_level, findings

[POS]
Server-side endpoint that collects Agent Profile data from DB, assembles
the ProfileAuditInput DTO, invokes the harness audit engine, and returns
the result. Zero LLM calls — pure deterministic assessment.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from myrm_agent_harness.agent.security.profile_audit import (
    ProfileAuditInput,
    run_profile_audit,
)
from myrm_agent_harness.agent.security.profile_audit.types import (
    CronJobInput,
    MCPConfigInput,
    SecurityPolicyInput,
    SkillScanInput,
    SubagentInput,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Agent, CronJobModel

logger = logging.getLogger(__name__)

router = APIRouter()

_DANGEROUS_TOOLS = frozenset({"shell_exec", "code_interpreter_tool", "file_write"})


@router.post("/{agent_id}/audit")
async def audit_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Run security audit on an Agent's profile configuration."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise not_found_error(resource="Agent")

    audit_input = await _build_audit_input(agent, db)
    result = run_profile_audit(audit_input)
    return success_response(data=result.to_dict())


async def _build_audit_input(agent: Agent, db: AsyncSession) -> ProfileAuditInput:
    """Assemble ProfileAuditInput DTO from Agent model and related data."""
    enabled_tools: list[str] = agent.enabled_builtin_tools or []
    mcp_servers: list[dict[str, object]] = agent.mcp_servers or []
    skill_ids: list[str] = agent.skill_ids or []
    subagent_ids: list[str] = agent.subagent_ids or []
    security_overrides: dict[str, object] = agent.security_overrides or {}

    mcp_configs = _build_mcp_configs(mcp_servers)
    skill_scans = await _build_skill_scans(skill_ids)
    subagents = await _build_subagent_inputs(subagent_ids, db)
    cron_jobs = await _build_cron_inputs(agent.id, enabled_tools, db)
    security_policy = _build_security_policy(security_overrides)

    return ProfileAuditInput(
        agent_id=agent.id,
        agent_name=agent.name or agent.id,
        enabled_builtin_tools=tuple(enabled_tools),
        mcp_configs=tuple(mcp_configs),
        skill_scans=tuple(skill_scans),
        subagents=tuple(subagents),
        cron_jobs=tuple(cron_jobs),
        security_policy=security_policy,
    )


def _build_mcp_configs(mcp_servers: list[dict[str, object]]) -> list[MCPConfigInput]:
    """Build MCP config inputs from Agent's stored MCP server list."""
    configs: list[MCPConfigInput] = []
    for mcp in mcp_servers:
        if not isinstance(mcp, dict):
            continue
        name = str(mcp.get("name", "unknown"))
        transport_type = str(mcp.get("type", "unknown"))
        has_auth = bool(mcp.get("headers") or mcp.get("auth"))
        configs.append(
            MCPConfigInput(
                server_name=name,
                transport_type=transport_type,
                has_auth=has_auth,
                finding_count=0,
                max_severity="",
            )
        )
    return configs


async def _build_skill_scans(skill_ids: list[str]) -> list[SkillScanInput]:
    """Build skill scan inputs from stored skill security summaries."""
    if not skill_ids:
        return []
    from app.core.skills.store.service import SkillsService

    scans: list[SkillScanInput] = []
    for sid in skill_ids:
        try:
            skill = await SkillsService.get_skill_by_id(sid)
        except Exception:
            logger.warning("Failed to fetch skill %s for audit, skipping", sid)
            continue
        if not skill:
            continue
        scan_summary = getattr(skill, "security_scan_summary", None)
        if scan_summary and isinstance(scan_summary, dict):
            scans.append(
                SkillScanInput(
                    skill_id=sid,
                    skill_name=skill.name or sid,
                    score=scan_summary.get("score", 100),
                    trust_recommendation=scan_summary.get("trust_recommendation", "trusted"),
                    finding_counts=scan_summary.get("finding_counts", {}),
                )
            )
    return scans


async def _build_subagent_inputs(subagent_ids: list[str], db: AsyncSession) -> list[SubagentInput]:
    """Build sub-agent inputs for recursive risk assessment."""
    if not subagent_ids:
        return []
    result = await db.execute(select(Agent).where(Agent.id.in_(subagent_ids)))
    inputs: list[SubagentInput] = []
    for sub in result.scalars():
        inputs.append(
            SubagentInput(
                agent_id=sub.id,
                agent_name=sub.name or sub.id,
                has_own_tools=bool(sub.enabled_builtin_tools),
                has_own_mcps=bool(sub.mcp_servers),
                has_own_subagents=bool(sub.subagent_ids),
            )
        )
    return inputs


async def _build_cron_inputs(agent_id: str, enabled_tools: list[str], db: AsyncSession) -> list[CronJobInput]:
    """Build cron job inputs for unattended execution risk assessment."""
    result = await db.execute(select(CronJobModel).where(CronJobModel.agent_id == agent_id))
    jobs: list[CronJobInput] = []
    for job in result.scalars():
        schedule_dict = job.schedule or {}
        schedule_str = schedule_dict.get("cron", str(schedule_dict))
        cron_tools = job.tools_allowed or list(enabled_tools)
        jobs.append(
            CronJobInput(
                job_id=job.id,
                schedule=str(schedule_str),
                agent_id=agent_id,
                has_dangerous_tools=bool(frozenset(cron_tools) & _DANGEROUS_TOOLS),
            )
        )
    return jobs


def _build_security_policy(overrides: dict[str, object]) -> SecurityPolicyInput:
    """Build security policy input from Agent's security overrides."""
    path_policy = overrides.get("pathPolicy")
    has_path = bool(isinstance(path_policy, dict) and path_policy.get("allowedRoots"))
    has_network = bool(overrides.get("networkAllowlist") or overrides.get("networkBlocklist"))
    has_caps = bool(overrides.get("capabilities"))
    timeout = overrides.get("approvalTimeoutSeconds")
    domain_hitl = bool(overrides.get("domainHitlEnabled"))

    return SecurityPolicyInput(
        has_path_policy=has_path,
        has_network_policy=has_network,
        has_capability_restrictions=has_caps,
        approval_timeout_seconds=int(timeout) if isinstance(timeout, (int, float)) else None,
        domain_hitl_enabled=domain_hitl,
    )
