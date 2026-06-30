"""Deploy backend protocol for agent-initiated artifact deployment.

[INPUT]
- app.services.deploy.types::DeployResult (POS: 部署结果数据类)

[OUTPUT]
- DeployBackend: Protocol — agent deploy_artifact 工具的后端契约

[POS]
Server 业务层 DeployBackend 协议；AgentDeployService 实现此接口。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.deploy.types import DeployResult


@runtime_checkable
class DeployBackend(Protocol):
    """Business-layer contract for artifact deployment backends."""

    async def preflight(self, artifact_id: str) -> tuple[bool, str]:
        """Return (deployable, message)."""
        ...

    async def execute_deploy(self, artifact_id: str) -> DeployResult:
        """Execute deployment for the given artifact."""
        ...

    async def get_artifact_name(self, artifact_id: str) -> str | None:
        """Return a human-readable artifact name, or None if not found."""
        ...
