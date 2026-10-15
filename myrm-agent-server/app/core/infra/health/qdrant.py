"""Qdrant health checker implementation.

[INPUT]
- myrm_agent_harness.infra.health::HealthChecker (POS: 健康检查抽象基类)
- app.config.settings::settings (POS: 应用配置)

[OUTPUT]
- QdrantHealthChecker: Qdrant资源健康检查

[POS]
Qdrant健康检查器。嵌入式 Qdrant 的数据目录由 OS 文件锁保护，持锁进程退出时由操作系统释放，这里的检查器仅负责基础的路径检查；
存储是否已回退为内存模式由 `system_status.vector_degraded` 表达。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.infra.health.health_checker import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    RecoveryResult,
    RecoveryStatus,
)

from app.config.settings import settings


class QdrantHealthChecker(HealthChecker):
    """Health checker for Qdrant embedded storage.

    Only the storage path is checked: the data directory lock is an OS file lock that is
    released when its holder exits, so there is no stale lock to detect or repair. Whether
    the store fell back to memory mode is reported by ``system_status.vector_degraded``.
    """

    def __init__(self) -> None:
        self.qdrant_path = Path(settings.database.qdrant_path)

    async def check(self) -> HealthCheckResult:
        """Check Qdrant storage health."""
        if not self.qdrant_path.exists():
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="Qdrant storage directory does not exist yet (first start)",
                details={"path": str(self.qdrant_path)},
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="Qdrant storage path verified. The data directory lock is released by the OS when its holder exits.",
            details={"path": str(self.qdrant_path)},
        )

    async def recover(self) -> RecoveryResult:
        """No manual recovery needed anymore."""
        return RecoveryResult(
            status=RecoveryStatus.SUCCESS,
            message="No manual recovery needed: the OS releases the data directory lock when its holder exits",
            actions_taken=["None"],
        )
