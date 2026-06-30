"""Deploy domain types for artifact deployment flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeployResult:
    """Structured result from a deployment attempt."""

    success: bool
    url: str
    deployment_id: str
    project_id: str
    status: str
    error: str | None = None
    latest_version_id: str | None = None
