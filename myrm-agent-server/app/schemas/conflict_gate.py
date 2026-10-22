"""
[INPUT]
- pydantic (BaseModel, Field)
- typing (Literal)

[OUTPUT]
- WriteMutationTypeLiteral, ConflictStatusLiteral, ResolutionStrategyLiteral
- WriteFingerprintDTO, WorkConflictItemDTO
- ConflictEvaluateRequestDTO, ConflictGateVerdictResponseDTO
- ConflictResolveRequestDTO, ConflictResolveResponseDTO

[POS]
Server 业务层多 Bot 并行产出冲突对账与合并前拦截门数据契约（Topic 12 · 第 19 项）。
定义写集指纹、冲突项、评估请求/响应与对账动作 DTO，杜绝 Any 类型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WriteMutationTypeLiteral = Literal[
    "file",
    "artifact",
    "config",
    "card",
]

ConflictStatusLiteral = Literal[
    "clean",
    "conflict_pending",
    "resolved",
]

ResolutionStrategyLiteral = Literal[
    "keep_worker_a",
    "keep_worker_b",
    "three_way_merge",
    "abort_both",
]


class WriteFingerprintDTO(BaseModel):
    """单个子代理写集指纹 DTO。"""

    worker_id: str = Field(..., description="产出修改的子代理工作者 ID")
    resource_id: str = Field(..., description="被修改的资源路径/标识 (如文件相对路径、工件 ID 或配置键)")
    mutation_type: WriteMutationTypeLiteral = Field(
        default="file", description="修改资源类型：file | artifact | config | card"
    )
    content_hash: str = Field(..., description="修改后内容的 SHA256/哈希摘要")
    summary: str = Field(default="", description="本次修改的简述描述")
    timestamp: str = Field(default="", description="写入时间戳 ISO 格式")


class WorkConflictItemDTO(BaseModel):
    """检测到的冲突条目 DTO。"""

    conflict_id: str = Field(..., description="冲突条目唯一标识")
    session_id: str = Field(..., description="关联的主会话 ID")
    resource_id: str = Field(..., description="冲突资源路径或标识")
    mutation_type: WriteMutationTypeLiteral = Field(..., description="冲突资源类型")
    worker_a: WriteFingerprintDTO = Field(..., description="产生冲突的 Worker A 写集指纹")
    worker_b: WriteFingerprintDTO = Field(..., description="产生冲突的 Worker B 写集指纹")
    status: ConflictStatusLiteral = Field(
        default="conflict_pending", description="冲突状态：conflict_pending | resolved"
    )
    resolution_strategy: ResolutionStrategyLiteral | None = Field(
        default=None, description="采纳的解决策略"
    )
    resolved_content: str | None = Field(default=None, description="解决后最终合并的内容文本")
    resolved_at: str | None = Field(default=None, description="对账解决时间戳 ISO 格式")


class ConflictEvaluateRequestDTO(BaseModel):
    """并行写集冲突评估请求 DTO。"""

    fingerprints: list[WriteFingerprintDTO] = Field(
        ..., description="并发 Worker 上报的待合并写集指纹列表"
    )


class ConflictGateVerdictResponseDTO(BaseModel):
    """写集冲突门禁裁决响应 DTO。"""

    session_id: str = Field(..., description="主会话 ID")
    is_blocked: bool = Field(..., description="是否存在未对账冲突导致合并阻断")
    total_conflicts: int = Field(..., ge=0, description="检出的冲突总数")
    conflicts: list[WorkConflictItemDTO] = Field(
        default_factory=list, description="详细冲突项列表"
    )
    clean_writes: list[WriteFingerprintDTO] = Field(
        default_factory=list, description="无碰撞安全写入列表"
    )


class ConflictResolveRequestDTO(BaseModel):
    """对账解决请求 DTO。"""

    strategy: ResolutionStrategyLiteral = Field(
        ...,
        description="对账策略：keep_worker_a | keep_worker_b | three_way_merge | abort_both",
    )
    resolved_content: str | None = Field(
        default=None,
        description="三方合并或人工对账时指定的最终内容文本",
    )


class ConflictResolveResponseDTO(BaseModel):
    """对账解决响应 DTO。"""

    conflict_id: str = Field(..., description="解决的冲突 ID")
    success: bool = Field(..., description="解决是否成功")
    message: str = Field(..., description="解决反馈说明")
    conflict: WorkConflictItemDTO | None = Field(default=None, description="解决后的冲突条目")
