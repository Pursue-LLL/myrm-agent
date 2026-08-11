"""Deployment capability gate for skills API.

Gates endpoints that install or manage local filesystem skills so they
fail closed in cloud sandbox mode, where local skills are disabled
(see ``app.platform_utils.deployment_capabilities``).

Installing to a store the agent cannot load is a silent failure, so every
local-skill install/import entry point shares this gate.
"""

from fastapi import HTTPException

from app.platform_utils.deployment_capabilities import get_deployment_capabilities


def require_local_skills_capability() -> None:
    """Raise 403 when the deployment does not allow local skills."""
    if not get_deployment_capabilities().allows_local_skills:
        raise HTTPException(
            status_code=403,
            detail="Local skills are not available in sandbox mode",
        )
