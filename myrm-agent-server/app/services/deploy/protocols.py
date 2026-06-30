"""Deploy backend protocol for agent-initiated artifact deployment."""

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
