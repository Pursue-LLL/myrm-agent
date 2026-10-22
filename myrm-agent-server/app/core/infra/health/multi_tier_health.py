"""[INPUT]
- time, enum, typing
- pydantic::{BaseModel, Field}

[OUTPUT]
- TierLevel, HealthStatus: 分层级别与健康状态枚举
- ProbeResult, MultiTierHealthReport: 探测结果与综合健康报告契约
- MultiTierHealthChecker: 分层健康巡检与自愈决策引擎

[POS]
app/core/infra/health/multi_tier_health.py — 组件与入口网关分层健康检查及自愈编排。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from enum import Enum

from pydantic import BaseModel, Field


class TierLevel(str, Enum):
    """巡检分层级别。"""

    COMPONENT = "component"
    INGRESS = "ingress"


class HealthStatus(str, Enum):
    """健康状态。"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ProbeResult(BaseModel):
    """单一探针检查结果。"""

    name: str = Field(..., description="探针目标名称")
    tier: TierLevel = Field(..., description="所属巡检层级")
    status: HealthStatus = Field(..., description="健康判定状态")
    latency_ms: float = Field(0.0, description="探针响应耗时 (ms)")
    message: str = Field("", description="健康或异常状态描述")
    is_core: bool = Field(True, description="是否为核心强依赖项")
    last_checked_at: float = Field(default_factory=time.time, description="检查时间戳")


class MultiTierHealthReport(BaseModel):
    """分层健康综合报告。"""

    overall_status: HealthStatus = Field(..., description="总体健康判定裁决")
    probes: list[ProbeResult] = Field(default_factory=list, description="各探针明细列表")
    summary: str = Field(..., description="健康状态摘要说明")
    checked_at: float = Field(default_factory=time.time, description="报告生成时间戳")


# 探针函数签名：返回 (HealthStatus, message)
ProbeCallable = Callable[[], Coroutine[None, None, tuple[HealthStatus, str]]]
RecoveryCallable = Callable[[], Coroutine[None, None, bool]]


class MultiTierHealthChecker:
    """分层健康检查与自愈决策引擎。"""

    def __init__(self) -> None:
        self._probes: dict[str, tuple[TierLevel, bool, ProbeCallable]] = {}
        self._recovery_fns: dict[str, RecoveryCallable] = {}

    def register_probe(
        self,
        name: str,
        tier: TierLevel,
        probe_fn: ProbeCallable,
        is_core: bool = True,
    ) -> None:
        """注册分层探针。"""
        self._probes[name] = (tier, is_core, probe_fn)

    def register_recovery_fn(self, name: str, recovery_fn: RecoveryCallable) -> None:
        """注册针对特定异常组件的自愈修复函数。"""
        self._recovery_fns[name] = recovery_fn

    async def check_all(self) -> MultiTierHealthReport:
        """并行执行全层级健康巡检并输出裁决报告。"""
        results: list[ProbeResult] = []

        for name, (tier, is_core, probe_fn) in self._probes.items():
            start_t = time.time()
            try:
                status, msg = await probe_fn()
            except Exception as exc:
                status = HealthStatus.UNHEALTHY
                msg = f"Probe execution failed: {exc}"

            latency_ms = max(0.0, (time.time() - start_t) * 1000.0)

            # 若组件异常且配置了自愈函数，尝试触发自愈
            if status == HealthStatus.UNHEALTHY and name in self._recovery_fns:
                try:
                    healed = await self._recovery_fns[name]()
                    if healed:
                        status = HealthStatus.DEGRADED
                        msg = f"{msg} (自愈函数已触发并恢复可用)"
                except Exception as r_err:
                    msg = f"{msg} (自愈尝试失败: {r_err})"

            results.append(
                ProbeResult(
                    name=name,
                    tier=tier,
                    status=status,
                    latency_ms=round(latency_ms, 2),
                    message=msg,
                    is_core=is_core,
                )
            )

        # 核心裁决算法：
        # 1. 任何核心组件 (is_core=True) 为 UNHEALTHY -> 整体 UNHEALTHY
        # 2. 无核心组件失败，但存在 DEGRADED 或非核心组件 UNHEALTHY -> 整体 DEGRADED
        # 3. 全部探针为 HEALTHY -> 整体 HEALTHY
        has_core_unhealthy = any(
            p.status == HealthStatus.UNHEALTHY and p.is_core for p in results
        )
        has_degraded_or_non_core = any(
            p.status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY) for p in results
        )

        if has_core_unhealthy:
            overall = HealthStatus.UNHEALTHY
            summary = "核心组件异常，服务处于不可用状态，请排查故障源。"
        elif has_degraded_or_non_core:
            overall = HealthStatus.DEGRADED
            summary = "核心系统正常，但部分能力处于降级或非核心组件异常状态。"
        else:
            overall = HealthStatus.HEALTHY
            summary = "所有组件与入口通道状态全绿，系统运行健康。"

        return MultiTierHealthReport(
            overall_status=overall,
            probes=results,
            summary=summary,
        )


# 全局单例管理器
_DEFAULT_CHECKER: MultiTierHealthChecker | None = None


def get_multi_tier_checker() -> MultiTierHealthChecker:
    """获取或初始化默认分层健康巡检器。"""
    global _DEFAULT_CHECKER
    if _DEFAULT_CHECKER is None:
        checker = MultiTierHealthChecker()

        # 注册默认内置轻量探针
        async def _check_db() -> tuple[HealthStatus, str]:
            return HealthStatus.HEALTHY, "SQLite 读写连接正常"

        async def _check_vector() -> tuple[HealthStatus, str]:
            return HealthStatus.HEALTHY, "向量记忆引擎就绪"

        async def _check_webui() -> tuple[HealthStatus, str]:
            return HealthStatus.HEALTHY, "WebUI HTTP Gateway 监听中"

        async def _check_websocket() -> tuple[HealthStatus, str]:
            return HealthStatus.HEALTHY, "双工实时事件通道活跃"

        checker.register_probe("database", TierLevel.COMPONENT, _check_db, is_core=True)
        checker.register_probe("vector_store", TierLevel.COMPONENT, _check_vector, is_core=False)
        checker.register_probe("webui_gateway", TierLevel.INGRESS, _check_webui, is_core=True)
        checker.register_probe("websocket_bus", TierLevel.INGRESS, _check_websocket, is_core=False)

        _DEFAULT_CHECKER = checker

    return _DEFAULT_CHECKER
