"""Multi-expert batch export orchestration (business layer).

[INPUT]
- ._export_closure::_Collector, _load_catalog, _load_servers, _unique_names (POS: expert closure collection)
- ._export_models::ExportError, ExportErrorCode, ExportPlan, ExpertDraft (POS: export contract models)
- ._export_render::PACKAGE_VERSION, corpus_of, spec_of (POS: corpus flattening and plugin bundle spec)
- app.services.agent.agent_service::AgentService (POS: expert profile retrieval)
- app.core.skills.packaging.redaction::redact_files, review_digest (POS: shared redaction review)
- myrm_agent_harness.agent.plugins::build_plugin_bundle (POS: bundle compiler)

[OUTPUT]
- build_multi_export_plan: (agent_ids, bundle_name) -> ExportPlan
- preview_multi_expert_export: (agent_ids, bundle_name) -> ExportPreview
- export_multi_expert: (agent_ids, ..., bundle_name) -> ExportedPackage

[POS]
Orchestrates multi-expert dependency closure, redaction review and Agent Plugins 1.0.0 ZIP
bundling for full-asset migration and batch sharing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace

from myrm_agent_harness.agent.plugins import build_plugin_bundle
from myrm_agent_harness.agent.plugins.models import PluginMcpServer, PluginSkill
from myrm_agent_harness.agent.plugins.rules import plugin_identity
from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.core.skills.packaging.redaction import redact_files
from app.core.skills.packaging.redaction import review_digest as compute_review_digest
from app.services.agent.agent_service import AgentService

from ._export_closure import (
    MAX_EXPORT_EXPERTS,
    _Collector,
    _load_catalog,
    _load_servers,
    _unique_names,
)
from ._export_models import (
    ExpertDraft,
    ExportedPackage,
    ExportError,
    ExportErrorCode,
    ExportPlan,
    ExportPreview,
)
from ._export_render import PACKAGE_VERSION, corpus_of, spec_of
from .agent_surface import profile_to_plugin_agent

__all__ = [
    "build_multi_export_plan",
    "export_multi_expert",
    "preview_multi_expert_export",
]

logger = logging.getLogger(__name__)


async def build_multi_export_plan(
    agent_ids: Sequence[str],
    bundle_name: str | None = None,
) -> ExportPlan:
    """Collect the dependency closure for multiple experts and unify them into one package."""
    if not agent_ids:
        raise ExportError(ExportErrorCode.EXPERT_NOT_FOUND, "No experts specified for batch export")

    roots = []
    seen_ids: set[str] = set()
    for raw_id in agent_ids:
        aid = raw_id.strip()
        if not aid or aid in seen_ids:
            continue
        seen_ids.add(aid)
        agent = await AgentService.get_agent_by_id(aid)
        if agent is None:
            raise ExportError(ExportErrorCode.EXPERT_NOT_FOUND, f"Expert '{aid}' not found")
        if agent.built_in:
            raise ExportError(ExportErrorCode.BUILT_IN_EXPERT, f"Built-in expert '{agent.display_name or aid}' cannot be exported")
        roots.append(agent)

    if not roots:
        raise ExportError(ExportErrorCode.EXPERT_NOT_FOUND, "No valid experts to export")

    catalog = await _load_catalog()
    servers = await _load_servers()
    collector = _Collector(catalog, servers)

    for root in roots:
        if len(collector._profiles) >= MAX_EXPORT_EXPERTS:
            break
        await collector.walk(root)

    root_ids = {r.id for r in roots}
    names = _unique_names(collector._profiles.values())
    drafts: list[ExpertDraft] = []
    workspace_files: dict[str, bytes] = {}

    for profile in collector._profiles.values():
        owner = names[profile.id]
        is_entry = profile.id in root_ids
        agent = profile_to_plugin_agent(
            profile,
            skill_names=await collector._bind_skills(profile, owner),
            mcp_names=collector._bind_connectors(profile, owner),
            subagent_names=tuple(names[child] for child in collector._children.get(profile.id, ())),
            is_subagent=not is_entry,
            is_entry_agent=is_entry,
        )
        drafts.append(ExpertDraft(profile.id, replace(agent, name=owner)))
        collector._report_unshared(profile, owner, is_entry=is_entry)
        if is_entry:
            workspace_files.update(collector._workspace(profile, owner))

    derived_name = bundle_name.strip() if bundle_name and bundle_name.strip() else f"{roots[0].display_name or 'myrm'}-bundle"

    checklist_bytes = _build_migration_checklist(
        roots=roots,
        drafts=drafts,
        skills=list(collector._skills.values()),
        connectors=list(collector._connectors.values()),
        preset_names=list(collector._preset_names),
    ).encode("utf-8")
    workspace_files["MIGRATION_CHECKLIST.md"] = checklist_bytes

    return ExportPlan(
        plugin_name=plugin_identity(derived_name, fallback="myrm-bundle"),
        experts=drafts,
        skills=list(collector._skills.values()),
        preset_skill_names=list(collector._preset_names),
        connectors=list(collector._connectors.values()),
        workspace_files=workspace_files,
        omitted=collector._omitted,
    )


def _build_migration_checklist(
    roots: Sequence[AgentProfile],
    drafts: Sequence[ExpertDraft],
    skills: Sequence[PluginSkill],
    connectors: Sequence[PluginMcpServer],
    preset_names: Sequence[str],
) -> str:
    lines = [
        "# 智能体全量资产迁移自省清单 (Agent Migration Checklist)",
        "",
        "## 📦 资产概览",
        f"- **包含智能体数**: {len(drafts)} 个（顶级入口: {len(roots)} 个）",
        f"- **包含自定义技能**: {len(skills)} 个",
        f"- **内置预设技能**: {len(preset_names)} 个",
        f"- **MCP 连接器**: {len(connectors)} 个",
        "- **规范标准**: Agent Plugins 1.0.0",
        "",
        "## 🤖 智能体清单",
    ]
    for draft in drafts:
        agent = draft.agent
        role = "入口智能体" if agent.is_entry_agent else "子智能体"
        lines.append(f"- **{agent.name}** ({role})")
        if agent.description:
            lines.append(f"  - 描述: {agent.description}")
        if agent.subagent_names:
            lines.append(f"  - 关联子智能体: {', '.join(agent.subagent_names)}")
        if agent.skill_names:
            lines.append(f"  - 依赖技能: {', '.join(agent.skill_names)}")
        if agent.mcp_names:
            lines.append(f"  - 依赖 MCP: {', '.join(agent.mcp_names)}")

    if skills:
        lines.extend(["", "## 🛠️ 自定义技能清单"])
        for skill in skills:
            lines.append(f"- **{skill.package_name}** (文件数: {len(skill.files)})")

    if connectors:
        lines.extend(["", "## 🔌 MCP 服务与目标环境变量清单"])
        for conn in connectors:
            lines.append(f"- **{conn.name}** (类型: {conn.server_type})")
            if conn.env_key_names:
                lines.append(f"  - 必需环境变量: {', '.join(conn.env_key_names)}")

    lines.extend([
        "",
        "## 🚀 目标环境一键恢复指引",
        "1. 在目标设备/沙箱中打开 Myrm WebUI 或 Desktop 桌面端。",
        "2. 前往「设置」->「智能体」(Settings -> Agents)。",
        "3. 点击「导入智能体」(Import Agent / Plugin) 按钮并选择此 ZIP 压缩包。",
        "4. 确认导入完成，即可无损恢复所有智能体拓扑与技能资产。",
    ])
    return "\n".join(lines) + "\n"


async def preview_multi_expert_export(
    agent_ids: Sequence[str],
    bundle_name: str | None = None,
) -> ExportPreview:
    """Collect the multi-expert closure, scan it and dry-run the package build."""
    plan = await build_multi_export_plan(agent_ids, bundle_name)
    corpus = corpus_of(plan)
    outcome = await asyncio.to_thread(redact_files, corpus, apply=False)
    built = await asyncio.to_thread(build_plugin_bundle, spec_of(plan, corpus))
    return ExportPreview(
        plan=plan,
        version=PACKAGE_VERSION,
        redactions=outcome.redactions,
        review_digest=compute_review_digest(corpus),
        package_bytes=len(built.zip_content) if built.success and built.zip_content else None,
        build_error=None if built.success else built.error,
    )


async def export_multi_expert(
    agent_ids: Sequence[str],
    *,
    apply_redactions: bool,
    ignored_redactions: Mapping[str, Sequence[int]] | None,
    review_digest: str | None,
    bundle_name: str | None = None,
) -> ExportedPackage:
    """Build the multi-expert package. Every finding must be redacted or explicitly kept."""
    plan = await build_multi_export_plan(agent_ids, bundle_name)
    corpus = corpus_of(plan)
    current_digest = compute_review_digest(corpus)

    outcome = await asyncio.to_thread(redact_files, corpus, apply=False)
    has_findings = any(outcome.redactions.values())

    if has_findings and not apply_redactions and not ignored_redactions:
        raise ExportError(ExportErrorCode.REVIEW_REQUIRED, "Redaction review required before export")

    if (ignored_redactions or apply_redactions) and review_digest is not None and review_digest != current_digest:
        raise ExportError(ExportErrorCode.CHANGED_SINCE_PREVIEW, "Content changed since review preview")

    final_outcome = await asyncio.to_thread(
        redact_files,
        corpus,
        apply=apply_redactions,
        ignored=ignored_redactions,
    )

    built = await asyncio.to_thread(build_plugin_bundle, spec_of(plan, final_outcome.files))
    if not built.success or not built.zip_content:
        raise ExportError(ExportErrorCode.PACKAGE_REJECTED, built.error or "Build failed")

    return ExportedPackage(
        zip_content=built.zip_content,
        filename=f"{plan.plugin_name}-{PACKAGE_VERSION}.zip",
    )
