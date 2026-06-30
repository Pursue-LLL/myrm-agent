"""Deploy domain types for artifact deployment flows.

[INPUT]
- (none — pure value types)

[OUTPUT]
- DeployResult: dataclass — REST 与 Agent 路径共用的部署结果

[POS]
Deploy 领域类型；被 vercel_artifact_deploy、deploy_api、deploy_agent_tools 引用。
"""

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
