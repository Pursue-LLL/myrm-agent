"""
[INPUT]
- fastapi (APIRouter, Depends, Query, status)
- app.schemas.infra_quota (
    QuotaCheckRequestDTO,
    QuotaCheckResultDTO,
    QuotaLimitsUpdateRequestDTO,
    QuotaUsageDeltaRequestDTO,
    UserInfraQuotaOverviewDTO,
  )
- app.services.agent.infra_quota_service (
    InfraQuotaService,
    get_infra_quota_service,
  )

[OUTPUT]
- router: 多 Agent 基础设施配额治理 REST API 路由对象

[POS]
Server 业务层每用户/组织多 Agent 基础设施配额治理 HTTP 端点（Topic 12 · 第 16 项）。
暴露四维配额概览查询、自助 Provision 准入门禁核验、用量变更与限额调整 API。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.infra_quota import (
    QuotaCheckRequestDTO,
    QuotaCheckResultDTO,
    QuotaLimitsUpdateRequestDTO,
    QuotaUsageDeltaRequestDTO,
    UserInfraQuotaOverviewDTO,
)
from app.services.agent.infra_quota_service import (
    InfraQuotaService,
    get_infra_quota_service,
)

router = APIRouter(prefix="/infra-quota", tags=["infra-quota-governance"])


@router.get(
    "/overview",
    response_model=UserInfraQuotaOverviewDTO,
    summary="查询多 Agent 基础设施配额全量概览与 Doctor 建议",
)
async def get_infra_quota_overview(
    user_id: str = Query(default="default_user", description="用户或组织标识"),
    service: InfraQuotaService = Depends(get_infra_quota_service),
) -> UserInfraQuotaOverviewDTO:
    """获取活跃 Agent、临时 DB、并发沙箱与持久 Volume 磁盘四维配额使用情况与 Doctor 建议。"""
    return service.get_user_quota_overview(user_id=user_id)


@router.post(
    "/check",
    response_model=QuotaCheckResultDTO,
    summary="自助 Provision 资源准入门禁核验 (Fail-Closed)",
)
async def check_infra_quota(
    request: QuotaCheckRequestDTO,
    user_id: str = Query(default="default_user", description="用户或组织标识"),
    service: InfraQuotaService = Depends(get_infra_quota_service),
) -> QuotaCheckResultDTO:
    """评估是否允许 Provision 指定资源量，若超限则返回 Fail-Closed 判定与修复指引。"""
    return service.check_quota(
        user_id=user_id,
        resource_type=request.resource_type,
        requested_amount=request.requested_amount,
    )


@router.post(
    "/consume",
    status_code=status.HTTP_200_OK,
    summary="变更指定资源用量 (申请或释放)",
)
async def consume_infra_quota(
    request: QuotaUsageDeltaRequestDTO,
    user_id: str = Query(default="default_user", description="用户或组织标识"),
    service: InfraQuotaService = Depends(get_infra_quota_service),
) -> dict[str, float]:
    """累加或释放资源用量，返回更新后的当前用量数值。"""
    updated = service.record_usage_delta(
        user_id=user_id,
        resource_type=request.resource_type,
        delta=request.delta_amount,
    )
    return {"updated_used": updated}


@router.put(
    "/limits",
    response_model=UserInfraQuotaOverviewDTO,
    summary="调整指定用户或组织的基础设施配额上限",
)
async def update_infra_quota_limits(
    request: QuotaLimitsUpdateRequestDTO,
    service: InfraQuotaService = Depends(get_infra_quota_service),
) -> UserInfraQuotaOverviewDTO:
    """更新配额限制，并返回更新后的最新概览视图。"""
    return service.update_quota_limits(request)
