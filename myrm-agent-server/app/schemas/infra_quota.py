"""
[INPUT]
- pydantic (BaseModel, Field)
- typing (Literal)

[OUTPUT]
- ResourceTypeLiteral: 四大核心基础设施资源类型字面量
- QuotaHealthStatusLiteral: 配额健康状态字面量
- ResourceQuotaUsageDTO: 单资源配额使用量与百分比 DTO
- UserInfraQuotaOverviewDTO: 用户基础设施配额全量概览与 Doctor 建议 DTO
- QuotaCheckRequestDTO: 资源预申请与准入门禁核验请求 DTO
- QuotaCheckResultDTO: 准入门禁核验结果与超限诊断 DTO
- QuotaUsageDeltaRequestDTO: 资源用量变更（增加或释放）请求 DTO
- QuotaLimitsUpdateRequestDTO: 配额上限变更请求 DTO

[POS]
Server 业务层每用户多 Agent 基础设施配额治理数据契约（Topic 12 · 第 16 项）。
对齐 TiDB Agent Stack 范式，严格管理活跃 Agent、临时 DB、并发沙箱与持久 Volume 磁盘配额，杜绝 Any 类型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ResourceTypeLiteral = Literal[
    "active_agents",
    "ephemeral_dbs",
    "concurrent_sandboxes",
    "volume_storage_gb",
]

QuotaHealthStatusLiteral = Literal["normal", "warning", "critical", "exhausted"]


class ResourceQuotaUsageDTO(BaseModel):
    """单项基础设施资源的用量与额度 DTO。"""

    resource_type: ResourceTypeLiteral = Field(..., description="资源类型标识")
    display_name: str = Field(..., description="人类可读资源名称")
    used: float = Field(..., ge=0.0, description="当前已占用量")
    limit: float = Field(..., gt=0.0, description="最大允许上限额度")
    unit: str = Field(default="count", description="度量单位 (count 或 GB)")
    usage_pct: float = Field(..., ge=0.0, description="用量占比百分比 (0-100+)")
    status: QuotaHealthStatusLiteral = Field(..., description="健康状态：normal | warning | critical | exhausted")


class UserInfraQuotaOverviewDTO(BaseModel):
    """用户级多 Agent 基础设施配额全量概览 DTO。"""

    user_id: str = Field(..., description="用户或组织标识")
    is_local_mode: bool = Field(default=True, description="是否处于单机/本地物理沙箱模式")
    quotas: list[ResourceQuotaUsageDTO] = Field(..., description="4 大维度资源配额明细")
    doctor_recommendations: list[str] = Field(default_factory=list, description="Doctor 智能降本排障建议")


class QuotaCheckRequestDTO(BaseModel):
    """自助 Provision 资源准入门禁核验请求 DTO。"""

    resource_type: ResourceTypeLiteral = Field(..., description="待申请的资源类型")
    requested_amount: float = Field(default=1.0, gt=0.0, description="拟申请的资源量")


class QuotaCheckResultDTO(BaseModel):
    """准入门禁核验结果 DTO。"""

    allowed: bool = Field(..., description="是否核准通过（Fail-Closed 判定）")
    resource_type: ResourceTypeLiteral = Field(..., description="资源类型")
    current_used: float = Field(..., description="当前已占用量")
    limit: float = Field(..., description="允许上限")
    requested_amount: float = Field(..., description="拟申请量")
    remaining_after: float = Field(..., description="核准后剩余可用额度")
    rejection_reason: str | None = Field(default=None, description="若拒绝时的明确超限原因")
    remediation_steps: list[str] = Field(default_factory=list, description="Doctor 修复建议指引")


class QuotaUsageDeltaRequestDTO(BaseModel):
    """用量变更（增加或释放）请求 DTO。"""

    resource_type: ResourceTypeLiteral = Field(..., description="资源类型")
    delta_amount: float = Field(..., description="变更量（正数代表新增占用，负数代表释放）")


class QuotaLimitsUpdateRequestDTO(BaseModel):
    """配额上限调整请求 DTO。"""

    user_id: str = Field(..., description="目标用户或组织 ID")
    active_agents_limit: float | None = Field(default=None, gt=0.0, description="活跃 Agent 数上限")
    ephemeral_dbs_limit: float | None = Field(default=None, gt=0.0, description="临时 DB 数量上限")
    concurrent_sandboxes_limit: float | None = Field(default=None, gt=0.0, description="并发沙箱数上限")
    volume_storage_gb_limit: float | None = Field(default=None, gt=0.0, description="Volume 存储上限 (GB)")
