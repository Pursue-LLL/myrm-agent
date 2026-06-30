"""Agent tool for artifact deployment to hosting platforms.

Single ``deploy_artifact`` tool: preflight → HITL approval → execute deploy.
Server business layer — not a harness toolkit primitive.

[INPUT]
- app.services.deploy.protocols::DeployBackend

[OUTPUT]
- create_deploy_tool: LangChain tool factory

[POS]
Agent-callable deploy tool for Myrm artifact → Vercel flow.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import BaseTool, tool

from app.services.deploy.protocols import DeployBackend
from app.services.deploy.types import DeployResult

logger = logging.getLogger(__name__)

__all__ = ["DeployBackend", "DeployResult", "create_deploy_tool"]


def _user_denied_deploy(response: object) -> bool:
    """Return True when the HITL response indicates user denial."""
    if not response:
        return True
    if not isinstance(response, dict):
        return False
    decision = response.get("decision")
    if decision in ("deny", "reject"):
        return True
    decisions = response.get("decisions")
    if isinstance(decisions, list) and decisions:
        first = decisions[0]
        if isinstance(first, dict) and first.get("type") in ("reject", "deny"):
            return True
    return False


def create_deploy_tool(backend: DeployBackend) -> list[BaseTool]:
    """Create the artifact deploy tool bound to a deployment backend."""

    @tool("deploy_artifact")
    async def deploy_artifact(artifact_id: str) -> str:
        """Deploy an artifact to a hosting platform.

        Use this tool ONLY when the user explicitly asks to deploy, publish,
        or put an artifact online. Do NOT call this for previewing artifacts.

        The tool will:
        1. Run a preflight check to verify the artifact is deployable.
        2. Request human approval before proceeding (the user must confirm).
        3. Execute the deployment and return the live URL.

        Args:
            artifact_id: The ID of the artifact to deploy. You can find this
                         from the artifact creation response or conversation context.
        """
        artifact_name = await backend.get_artifact_name(artifact_id)
        display_name = artifact_name or artifact_id[:8]

        deployable, preflight_msg = await backend.preflight(artifact_id)
        if not deployable:
            return (
                f"Cannot deploy \"{display_name}\": {preflight_msg}\n\n"
                "If this is a code artifact (React/Vue/etc.), ask the user to "
                "export it as a complete HTML artifact first, then try deploying again."
            )

        from langgraph.types import interrupt

        approval_payload = {
            "action_type": "deploy_approval",
            "reason": f'Request to deploy artifact "{display_name}" to Vercel.',
            "severity": "warning",
            "payload": {
                "artifact_id": artifact_id,
                "artifact_name": display_name,
                "message": f'Deploy "{display_name}" to Vercel?',
            },
        }
        response = interrupt(approval_payload)

        if _user_denied_deploy(response):
            return f"Deployment of \"{display_name}\" was cancelled by the user."

        try:
            result = await backend.execute_deploy(artifact_id)
        except Exception as exc:
            logger.error("Deployment failed for artifact %s: %s", artifact_id, exc)
            return f"Deployment failed: {exc}"

        if not result.success:
            return f"Deployment failed: {result.error or result.status}"

        return json.dumps(
            {
                "status": "success",
                "url": result.url,
                "deployment_id": result.deployment_id,
                "project_id": result.project_id,
                "message": f"Successfully deployed \"{display_name}\" to {result.url}",
            },
            ensure_ascii=False,
        )

    return [deploy_artifact]
