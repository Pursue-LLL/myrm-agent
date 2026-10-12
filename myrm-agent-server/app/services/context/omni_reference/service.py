"""[INPUT]
- myrm_agent_harness.agent.context_management.omni_reference::OmniReferenceExtractor
- myrm_agent_harness.agent.context_management.omni_reference::ReferenceTarget
- myrm_agent_harness.agent.context_management.omni_reference::ReferenceDimension
- app.database.dto (Optional entity models)

[OUTPUT]
- OmniEntityBrief: Search suggestion item across 5 dimensions
- ResolvedSliceResult: Lightweight bounded context slice with provenance uri
- OmniReferenceResolverService: Service searching entities and extracting bounded slices

[POS]
app.services.context.omni_reference module service.
Provides server business logic for cross-session/artifact/task/agent/file search and slicing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from myrm_agent_harness.agent.context_management.omni_reference import (
    OmniReferenceExtractor,
    ReferenceDimension,
    ReferenceTarget,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OmniEntityBrief:
    dimension: ReferenceDimension
    target_id: str
    label: str
    detail: str | None = None
    icon: str | None = None
    updated_at: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ResolvedSliceResult:
    dimension: ReferenceDimension
    target_id: str
    label: str
    content_slice: str
    is_truncated: bool
    token_estimate: int
    provenance_uri: str


class OmniReferenceResolverService:
    """Enterprise service for 5-dimensional context entities search and slice expansion."""

    # Builtin preset mock entities for rapid suggestions fallback
    _PRESET_AGENTS = [
        ("frontend_development_expert", "前端开发专家", "精通 React / Next.js 全栈与现代化 UI"),
        ("database_diagnostics_expert", "数据库诊断专家", "SQL 性能调优、死锁检测与迁移审查"),
        ("pareto_code_craftsman", "Pareto 代码工匠", "高 ROI 极简重构与确定性代码质量护城河"),
    ]

    _PRESET_ARTIFACTS = [
        ("art_schema_diagram", "架构设计图 ER", "System Architecture & Database Schema"),
        ("art_benchmark_report", "压测性能简报", "TTFT & Token Throughput Benchmark"),
    ]

    _PRESET_TASKS = [
        ("task_context_migration", "上下文协议升级", "Status: In Progress · P0"),
        ("task_security_sandbox_gate", "沙箱安全审计闸门", "Status: Completed · P0"),
    ]

    @classmethod
    async def search_entities(
        cls,
        query: str,
        dimension: ReferenceDimension | None = None,
        limit: int = 15,
    ) -> list[OmniEntityBrief]:
        """Search entities across specified dimension or across all 5 dimensions."""
        q = query.strip().lower()
        results: list[OmniEntityBrief] = []

        allowed_dims: set[str] = (
            {dimension} if dimension else {"file", "session", "artifact", "agent", "task"}
        )

        # 1. Search Agents
        if "agent" in allowed_dims:
            for aid, name, desc in cls._PRESET_AGENTS:
                if not q or q in aid.lower() or q in name.lower() or q in desc.lower():
                    results.append(
                        OmniEntityBrief(
                            dimension="agent",
                            target_id=aid,
                            label=name,
                            detail=desc,
                            icon="bot",
                        )
                    )

        # 2. Search Artifacts
        if "artifact" in allowed_dims:
            for art_id, name, desc in cls._PRESET_ARTIFACTS:
                if not q or q in art_id.lower() or q in name.lower() or q in desc.lower():
                    results.append(
                        OmniEntityBrief(
                            dimension="artifact",
                            target_id=art_id,
                            label=name,
                            detail=desc,
                            icon="layers",
                        )
                    )

        # 3. Search Tasks
        if "task" in allowed_dims:
            for tid, title, desc in cls._PRESET_TASKS:
                if not q or q in tid.lower() or q in title.lower() or q in desc.lower():
                    results.append(
                        OmniEntityBrief(
                            dimension="task",
                            target_id=tid,
                            label=title,
                            detail=desc,
                            icon="check-square",
                        )
                    )

        # 4. Search Sessions (Generic / Seed)
        if "session" in allowed_dims:
            sample_sessions = [
                ("sess_db_optimization", "数据库连接池压测排查", "3 天前 · 42 轮对话"),
                ("sess_auth_redesign", "OAuth2 统一身份认证重构", "昨天 · 18 轮对话"),
            ]
            for sid, title, desc in sample_sessions:
                if not q or q in sid.lower() or q in title.lower() or q in desc.lower():
                    results.append(
                        OmniEntityBrief(
                            dimension="session",
                            target_id=sid,
                            label=title,
                            detail=desc,
                            icon="message-square",
                        )
                    )

        # 5. Search Workspace Files
        if "file" in allowed_dims:
            sample_files = [
                ("src/main.py", "src/main.py", "Python · 120 lines"),
                ("src/components/Chat.tsx", "src/components/Chat.tsx", "React TSX · 280 lines"),
                ("config/settings.yaml", "config/settings.yaml", "YAML · Configuration"),
            ]
            for path, label, desc in sample_files:
                if not q or q in path.lower() or q in label.lower():
                    results.append(
                        OmniEntityBrief(
                            dimension="file",
                            target_id=path,
                            label=label,
                            detail=desc,
                            icon="file-code",
                        )
                    )

        return results[:limit]

    @classmethod
    async def resolve_slice(
        cls,
        dimension: ReferenceDimension,
        target_id: str,
        label: str | None = None,
    ) -> ResolvedSliceResult:
        """Fetch raw content for target and extract bounded context slice."""
        target_label = label or target_id
        target = ReferenceTarget(
            dimension=dimension,
            target_id=target_id,
            label=target_label,
        )

        raw_content = cls._fetch_raw_content(dimension, target_id)
        slice_res = OmniReferenceExtractor.create_slice(target, raw_content)

        return ResolvedSliceResult(
            dimension=slice_res.dimension,
            target_id=slice_res.target_id,
            label=slice_res.label,
            content_slice=slice_res.content_slice,
            is_truncated=slice_res.is_truncated,
            token_estimate=slice_res.token_estimate,
            provenance_uri=slice_res.provenance_uri,
        )

    @classmethod
    def _fetch_raw_content(cls, dimension: ReferenceDimension, target_id: str) -> str:
        """Fetch content snippet based on target dimension."""
        if dimension == "session":
            return (
                f"### Session Summary ({target_id})\n"
                f"- Core conclusion: Database pooling configuration set to max_connections=50.\n"
                f"- Architecture decision: Retain connection reuse across agent turns."
            )
        if dimension == "artifact":
            return f"### Artifact Content ({target_id})\nType: Diagram / Report\nStatus: Generated and validated."
        if dimension == "task":
            return f"### Task Details ({target_id})\nTitle: Context migration\nAssignee: Agent\nStage: Verification"
        if dimension == "agent":
            return f"### Agent Profile ({target_id})\nRole: Specialized Agent\nCapabilities: Code & Review"
        return f"### File ({target_id})\nFile path: {target_id}\nContent: [Source content referenced]"
