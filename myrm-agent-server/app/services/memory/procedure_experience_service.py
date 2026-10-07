# [POS]: app/services/memory/procedure_experience_service.py
# [INPUT]: app.schemas.procedure_experience, myrm_agent_harness.toolkits.memory
# [OUTPUT]: ProcedureExperienceService, get_procedure_experience_service

from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    DualNodeFixedCountRetriever,
    DualNodeRetrievalQuery,
    ProcedureMemoryEntry,
    ProcedureProtocolEngine,
    RetrievalNodeKind,
)

from app.schemas.procedure_experience import (
    DualNodeRetrievalRequest,
    DualNodeRetrievalResponseDTO,
    MultiIntentSplitResponseDTO,
    ProcedureMemoryEntryDTO,
    ProtocolValidationResponseDTO,
    RegisterProcedureMemoryRequest,
)

logger = logging.getLogger(__name__)


class ProcedureExperienceService:
    """Service managing 8-field procedure-shaped experiences and fixed-count dual-node retrieval."""

    def __init__(
        self,
        retriever: DualNodeFixedCountRetriever | None = None,
        protocol_engine: ProcedureProtocolEngine | None = None,
    ) -> None:
        self._protocol_engine = protocol_engine or ProcedureProtocolEngine()
        self._retriever = retriever or DualNodeFixedCountRetriever(protocol_engine=self._protocol_engine)
        self._seed_default_procedures()

    def _seed_default_procedures(self) -> None:
        """Seed industrial-standard procedure entries demonstrating the 8-field protocol."""
        deploy_proc = ProcedureMemoryEntry(
            entry_id="proc_deploy_ci_01",
            name="生产发布门禁流水线规范",
            retrieval_anchor="intent:deploy-ci-pipeline|pre:lint-clean,vitest-pass|app:production,release",
            operation_intent="在将代码发布或合并至主分支前，执行严格的代码质量与无障碍门禁检查",
            preconditions=[
                "工作区无未暂存的致命破坏性代码变更",
                "Python 单测与前端 Vitest 单测均已全量运行",
            ],
            immutable_boundary=[
                "禁止直接使用 git push -f 覆盖主分支",
                "禁止为了省事而跳过 a11y ratchet 门禁",
            ],
            procedure_steps=[
                "1. 执行 bun run lint 并确保 0 errors",
                "2. 执行 bun scripts/check-a11y-ratchet.mjs 校验 0 违规",
                "3. 执行 pytest 验证框架与服务层全部回归通过",
                "4. 确认代码单文件行数严格控制在 400 行以内",
            ],
            write_field_provenance={
                "gate_status": "从 vitest 和 ruff 输出解析出的最终退出状态码",
                "coverage_metrics": "单测汇总的 pass/fail 条数统计",
            },
            anti_patterns=[
                "绝不使用 any 类型注解，必须声明严格的具体类型",
                "绝不在修复 lint 时静默删除已有功能逻辑",
            ],
            applicability=[
                "代码提交前的 pre-commit 审查",
                "向远程生产环境部署应用时的自动化工作流",
            ],
            negative_applicability=[
                "临时本地调试原型开发且不打算提交的单机沙盒阶段",
            ],
            confidence=1.0,
        )
        self._retriever.register(deploy_proc)

        data_isolation_proc = ProcedureMemoryEntry(
            entry_id="proc_data_isolation_02",
            name="写前租户隔离与防越权校验",
            retrieval_anchor="intent:write-isolation-check|pre:session-scope-valid|app:database,mutation",
            operation_intent="在执行持久化数据写操作前，强制执行作用域范围与租户隔离物理边界校验",
            preconditions=[
                "拥有明确的当前会话 session_id 或工作区作用域",
                "已获取待写入实体或记忆的归属上下文",
            ],
            immutable_boundary=[
                "禁止跨作用域污染全局未授权资产",
                "严格保证单机沙盒内部存储不发生跨用户泄露",
            ],
            procedure_steps=[
                "1. 提取当前调用上下文的 scope 与 session 标识",
                "2. 校验写入目标数据表对应的 WHERE 条件已绑定专属作用域",
                "3. 执行写入并记录操作审计指纹",
            ],
            write_field_provenance={
                "audit_fingerprint": "由时间戳与操作数据 SHA256 摘要派生",
            },
            anti_patterns=[
                "在没有 scope 过滤条件的情况下执行盲目批量更新",
            ],
            applicability=[
                "所有涉及数据库 INSERT/UPDATE/DELETE 的写操作前",
            ],
            negative_applicability=[
                "纯内存态临时只读计算，无任何磁盘持久化改动的场景",
            ],
            confidence=1.0,
        )
        self._retriever.register(data_isolation_proc)

    def register_entry(self, request: RegisterProcedureMemoryRequest) -> ProcedureMemoryEntryDTO:
        """Register a new procedure entry with 8-field protocol conformance verification."""
        entry_id = request.entry_id or f"proc_{uuid.uuid4().hex[:8]}"

        anchor = request.retrieval_anchor or self._protocol_engine.generate_retrieval_anchor(
            operation_intent=request.operation_intent,
            preconditions=request.preconditions,
            applicability=request.applicability,
        )

        domain_entry = ProcedureMemoryEntry(
            entry_id=entry_id,
            name=request.name,
            retrieval_anchor=anchor,
            operation_intent=request.operation_intent,
            preconditions=list(request.preconditions),
            immutable_boundary=list(request.immutable_boundary),
            procedure_steps=list(request.procedure_steps),
            write_field_provenance=dict(request.write_field_provenance),
            anti_patterns=list(request.anti_patterns),
            applicability=list(request.applicability),
            negative_applicability=list(request.negative_applicability),
            confidence=request.confidence,
            source_session_id=request.source_session_id,
        )

        registered = self._retriever.register(domain_entry)
        return self._to_dto(registered)

    def retrieve(self, request: DualNodeRetrievalRequest) -> DualNodeRetrievalResponseDTO:
        """Execute fixed-count dual-node retrieval targeting first-user or pre-write intercept sites."""
        node_kind = (
            RetrievalNodeKind.PRE_WRITE
            if request.node_kind == "pre_write"
            else RetrievalNodeKind.FIRST_USER
        )

        query = DualNodeRetrievalQuery(
            query_text=request.query_text,
            node_kind=node_kind,
            top_n=request.top_n,
            scope_filter=request.scope_filter,
        )

        result = self._retriever.retrieve(query)
        dtos = [self._to_dto(e) for e in result.matched_entries]

        return DualNodeRetrievalResponseDTO(
            node_kind=node_kind.value,
            top_n_requested=request.top_n,
            total_matched=result.total_matched,
            matched_entries=dtos,
        )

    def validate_protocol(self, entry: ProcedureMemoryEntry) -> ProtocolValidationResponseDTO:
        """Check 8-field protocol conformance."""
        violations = self._protocol_engine.validate_protocol(entry)
        return ProtocolValidationResponseDTO(
            is_valid=len(violations) == 0,
            violations=violations,
        )

    def split_intents(self, raw_text: str) -> MultiIntentSplitResponseDTO:
        """Decompose multi-intent raw traces into distinct single-intent fragments."""
        fragments = self._protocol_engine.split_multi_intent_raw_steps(raw_text)
        return MultiIntentSplitResponseDTO(
            fragment_count=len(fragments),
            fragments=fragments,
        )

    def list_entries(self) -> list[ProcedureMemoryEntryDTO]:
        """List all registered procedure memory entries."""
        return [self._to_dto(e) for e in self._retriever.list_all()]

    def get_entry(self, entry_id: str) -> ProcedureMemoryEntryDTO | None:
        """Retrieve entry by unique identifier."""
        entry = self._retriever.get_entry(entry_id)
        return self._to_dto(entry) if entry else None

    @staticmethod
    def _to_dto(e: ProcedureMemoryEntry) -> ProcedureMemoryEntryDTO:
        return ProcedureMemoryEntryDTO(
            entry_id=e.entry_id,
            name=e.name,
            retrieval_anchor=e.retrieval_anchor,
            operation_intent=e.operation_intent,
            preconditions=list(e.preconditions),
            immutable_boundary=list(e.immutable_boundary),
            procedure_steps=list(e.procedure_steps),
            write_field_provenance=dict(e.write_field_provenance),
            anti_patterns=list(e.anti_patterns),
            applicability=list(e.applicability),
            negative_applicability=list(e.negative_applicability),
            confidence=e.confidence,
            source_session_id=e.source_session_id,
            created_at=e.created_at,
        )


@lru_cache
def get_procedure_experience_service() -> ProcedureExperienceService:
    """Singleton provider for procedure experience service."""
    return ProcedureExperienceService()
