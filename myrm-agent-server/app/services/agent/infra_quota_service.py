"""
[INPUT]
- typing (Literal)
- app.config.deploy_mode (is_local_mode)
- app.schemas.infra_quota (
    QuotaCheckResultDTO,
    QuotaHealthStatusLiteral,
    QuotaLimitsUpdateRequestDTO,
    ResourceQuotaUsageDTO,
    ResourceTypeLiteral,
    UserInfraQuotaOverviewDTO,
  )

[OUTPUT]
- InfraQuotaService: 每用户/组织多 Agent 基础设施配额治理服务
- get_infra_quota_service: 获取单例治理服务实例工厂

[POS]
Server 业务层多 Agent 基础设施资源配额治理服务（Topic 12 · 第 16 项）。
对齐 TiDB Agent Stack 范式，为活跃 Agent、临时 DB、并发沙箱与 Volume 磁盘提供准入门禁与 Doctor 调优。
"""

from __future__ import annotations

from app.config.deploy_mode import is_local_mode
from app.schemas.infra_quota import (
    QuotaCheckResultDTO,
    QuotaHealthStatusLiteral,
    QuotaLimitsUpdateRequestDTO,
    ResourceQuotaUsageDTO,
    ResourceTypeLiteral,
    UserInfraQuotaOverviewDTO,
)

DEFAULT_QUOTA_CONFIGS: dict[ResourceTypeLiteral, tuple[str, float, str]] = {
    "active_agents": ("活跃智能体数量", 20.0, "count"),
    "ephemeral_dbs": ("临时工作数据库", 10.0, "count"),
    "concurrent_sandboxes": ("并发执行沙箱", 5.0, "count"),
    "volume_storage_gb": ("持久卷磁盘空间", 50.0, "GB"),
}


class InfraQuotaService:
    """每用户/组织多 Agent 基础设施配额治理业务服务。"""

    def __init__(self) -> None:
        # 结构：user_id -> resource_type -> used_amount
        self._usage_store: dict[str, dict[ResourceTypeLiteral, float]] = {}
        # 结构：user_id -> resource_type -> limit_amount
        self._custom_limits: dict[str, dict[ResourceTypeLiteral, float]] = {}

    def get_user_quota_overview(self, user_id: str) -> UserInfraQuotaOverviewDTO:
        """获取指定用户的四维基础设施配额使用情况与 Doctor 建议。"""
        usages = self._usage_store.setdefault(user_id, {k: 0.0 for k in DEFAULT_QUOTA_CONFIGS})
        limits = self._get_effective_limits(user_id)

        quota_items: list[ResourceQuotaUsageDTO] = []
        doctor_notes: list[str] = []

        for r_type, (display_name, _, unit) in DEFAULT_QUOTA_CONFIGS.items():
            used = usages.get(r_type, 0.0)
            limit = limits.get(r_type, 1.0)
            pct = round((used / limit) * 100, 1) if limit > 0 else 100.0

            status: QuotaHealthStatusLiteral
            if pct >= 100.0:
                status = "exhausted"
            elif pct >= 90.0:
                status = "critical"
            elif pct >= 70.0:
                status = "warning"
            else:
                status = "normal"

            quota_items.append(
                ResourceQuotaUsageDTO(
                    resource_type=r_type,
                    display_name=display_name,
                    used=used,
                    limit=limit,
                    unit=unit,
                    usage_pct=pct,
                    status=status,
                )
            )

            # Doctor 启发式降本调优规则
            if status in ("warning", "critical", "exhausted"):
                if r_type == "active_agents":
                    doctor_notes.append(
                        f"活跃 Agent 占用已达 {pct}%（{used:.0f}/{limit:.0f}）：建议休眠无任务长挂的闲置 Agent，释放调度内存。"
                    )
                elif r_type == "volume_storage_gb":
                    doctor_notes.append(
                        f"持久 Volume 磁盘已占用 {pct}%（{used:.1f}/{limit:.1f} GB）：建议清空历史构建临时缓存或归档冷数据。"
                    )
                elif r_type == "concurrent_sandboxes":
                    doctor_notes.append(
                        f"并发沙箱占位已达 {pct}%（{used:.0f}/{limit:.0f}）：建议开启执行队列排队或复用同宿主微沙箱。"
                    )
                elif r_type == "ephemeral_dbs":
                    doctor_notes.append(
                        f"临时工作 DB 已占用 {pct}%（{used:.0f}/{limit:.0f}）：建议及时收割已完成迭代任务的临时 SQLite/DuckDB 实例。"
                    )

        if not doctor_notes:
            doctor_notes.append("当前多 Agent 基础设施各维度配额充裕，资源水线健康。")

        return UserInfraQuotaOverviewDTO(
            user_id=user_id,
            is_local_mode=is_local_mode(),
            quotas=quota_items,
            doctor_recommendations=doctor_notes,
        )

    def check_quota(
        self,
        user_id: str,
        resource_type: ResourceTypeLiteral,
        requested_amount: float = 1.0,
    ) -> QuotaCheckResultDTO:
        """
        自助 Provision 资源准入门禁（Fail-Closed 判定）。
        若申请后超过限制，拦截并返回拒绝成因与修复指引。
        """
        usages = self._usage_store.setdefault(user_id, {k: 0.0 for k in DEFAULT_QUOTA_CONFIGS})
        limits = self._get_effective_limits(user_id)

        current_used = usages.get(resource_type, 0.0)
        limit = limits.get(resource_type, 1.0)
        projected = current_used + requested_amount

        allowed = projected <= limit
        remaining_after = max(0.0, limit - projected)

        rejection_reason: str | None = None
        remediation_steps: list[str] = []

        if not allowed:
            display_name = DEFAULT_QUOTA_CONFIGS.get(resource_type, (resource_type, 0.0, ""))[0]
            unit = DEFAULT_QUOTA_CONFIGS.get(resource_type, ("", 0.0, "count"))[2]
            rejection_reason = (
                f"基础设施配额不足：拟申请 {requested_amount} {unit} {display_name}，"
                f"将导致用量达到 {projected:.1f} {unit}，超出上限 {limit:.1f} {unit}。"
            )
            remediation_steps = [
                f"清理或释放已不需要的 {display_name} 资源占用",
                "参考 Doctor 诊断建议归档冷态数据或休眠非关键任务 Agent",
                "若处于高强度业务场景，可调整当前组织配额上限",
            ]

        return QuotaCheckResultDTO(
            allowed=allowed,
            resource_type=resource_type,
            current_used=current_used,
            limit=limit,
            requested_amount=requested_amount,
            remaining_after=remaining_after,
            rejection_reason=rejection_reason,
            remediation_steps=remediation_steps,
        )

    def record_usage_delta(
        self,
        user_id: str,
        resource_type: ResourceTypeLiteral,
        delta: float,
    ) -> float:
        """更新资源用量（delta > 0 为占用，delta < 0 为释放）。"""
        usages = self._usage_store.setdefault(user_id, {k: 0.0 for k in DEFAULT_QUOTA_CONFIGS})
        current = usages.get(resource_type, 0.0)
        updated = max(0.0, current + delta)
        usages[resource_type] = updated
        return updated

    def update_quota_limits(
        self,
        request: QuotaLimitsUpdateRequestDTO,
    ) -> UserInfraQuotaOverviewDTO:
        """更新指定用户或组织的配额上限。"""
        user_limits = self._custom_limits.setdefault(request.user_id, {})
        if request.active_agents_limit is not None:
            user_limits["active_agents"] = request.active_agents_limit
        if request.ephemeral_dbs_limit is not None:
            user_limits["ephemeral_dbs"] = request.ephemeral_dbs_limit
        if request.concurrent_sandboxes_limit is not None:
            user_limits["concurrent_sandboxes"] = request.concurrent_sandboxes_limit
        if request.volume_storage_gb_limit is not None:
            user_limits["volume_storage_gb"] = request.volume_storage_gb_limit

        return self.get_user_quota_overview(request.user_id)

    def _get_effective_limits(self, user_id: str) -> dict[ResourceTypeLiteral, float]:
        """计算指定用户的生效上限。"""
        effective: dict[ResourceTypeLiteral, float] = {k: v[1] for k, v in DEFAULT_QUOTA_CONFIGS.items()}
        custom = self._custom_limits.get(user_id, {})
        effective.update(custom)
        return effective


_GLOBAL_INFRA_QUOTA_SERVICE: InfraQuotaService | None = None


def get_infra_quota_service() -> InfraQuotaService:
    """获取单例配额治理服务实例。"""
    global _GLOBAL_INFRA_QUOTA_SERVICE
    if _GLOBAL_INFRA_QUOTA_SERVICE is None:
        _GLOBAL_INFRA_QUOTA_SERVICE = InfraQuotaService()
    return _GLOBAL_INFRA_QUOTA_SERVICE
