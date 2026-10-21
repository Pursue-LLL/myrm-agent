"""Manual sandbox container recreate (SaaS sandbox mode only).

[INPUT]
- app.api.system.schemas::SandboxRecreateRequest, SandboxRecreateResponse (POS: System API Schemas)
- app.core.agent.run_activity::active_background_agent_runs (POS: agent runs that bypass AgentGateway)
- app.services.agent.gateway::get_agent_gateway (POS: Agent 执行网关，并发控制与生命周期)
- app.services.infra.python_env_reset::request_python_env_reset, cancel_python_env_reset (POS: deferred Python environment reset)
- myrm_agent_harness.api.hooks::count_running_background_shell_jobs (POS: background shell safety probe)

[OUTPUT]
- recreate_sandbox_container: POST /sandbox/recreate — ask the control plane to swap this container for a fresh one

[POS]
User-initiated environment reset. The control plane stops the old container with a short grace period (Docker's
10 s stop window), so the route refuses while shell jobs or agent runs would be killed mid-way instead of draining them.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException
from myrm_agent_harness.api.hooks import count_running_background_shell_jobs

from app.api.system.schemas import SandboxRecreateRequest, SandboxRecreateResponse
from app.config.settings import get_settings
from app.core.agent.run_activity import active_background_agent_runs
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.services.agent.gateway import get_agent_gateway
from app.services.infra.python_env_reset import cancel_python_env_reset, request_python_env_reset

logger = logging.getLogger(__name__)

router = APIRouter()


def _agent_work_in_flight() -> bool:
    """Whether any agent run (chat turn, cron, IM channel, kanban, eval, sub-agent) is executing in this process."""
    gateway = get_agent_gateway()
    return bool(gateway.active_session_ids()) or gateway.active_count > 0 or active_background_agent_runs() > 0


async def _request_container_swap(cp_url: str, sandbox_id: str, token: str) -> None:
    """Ask the control plane to replace this container; it answers once the swap is committed."""
    recreate_url = f"{cp_url}/api/internal/sandboxes/{sandbox_id}/recreate"
    headers = {
        "X-Telemetry-Token": token,
        "X-Sandbox-Id": sandbox_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(recreate_url, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("CP recreate request error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to reach control plane",
        ) from exc

    if resp.status_code >= 400:
        logger.error(
            "CP recreate request failed: %s %s",
            resp.status_code,
            resp.text[:200],
        )
        raise HTTPException(
            status_code=502,
            detail=f"Control plane returned {resp.status_code}",
        )


@router.post("/sandbox/recreate", response_model=SandboxRecreateResponse)
async def recreate_sandbox_container(request: SandboxRecreateRequest | None = None) -> SandboxRecreateResponse:
    """Trigger container recreation via the Control Plane.

    The persistent volume (workspace files, chats, memory, settings) is kept and the container is replaced by a
    fresh one. With ``reset_python_env`` the packages the agent installed are also cleared; that happens at the
    next start because this process still has the environment in use.

    The server process terminates when the old container is destroyed,
    so this endpoint fires the CP request and returns immediately.
    """
    caps = get_deployment_capabilities()
    if not caps.is_sandbox_instance:
        raise HTTPException(
            status_code=403,
            detail="Container recreate is only available in sandbox mode",
        )

    settings = get_settings()
    cp_url = settings.control_plane.effective_url()
    sandbox_id = settings.control_plane.sandbox_id
    token = settings.control_plane.telemetry_token.get_secret_value()

    if not sandbox_id or not token:
        raise HTTPException(
            status_code=503,
            detail="Control plane connectivity not configured",
        )

    if count_running_background_shell_jobs() > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot recreate container while background shell job(s) are still running. Cancel or wait for them to finish first.",
        )

    if _agent_work_in_flight():
        raise HTTPException(
            status_code=409,
            detail="Cannot recreate container while an agent run is still in progress. Stop it or wait for it to finish first.",
        )

    placed_reset_request = request is not None and request.reset_python_env and await asyncio.to_thread(request_python_env_reset)

    try:
        await _request_container_swap(cp_url, sandbox_id, token)
    except BaseException:
        # Only an accepted swap keeps the request. After a failure or a cancellation (outcome unknown) a request left
        # behind could wipe packages on an unrelated later restart, while a withdrawn one costs at most a repeat click.
        # A request placed by an earlier, accepted click is not ours to withdraw.
        if placed_reset_request:
            await asyncio.to_thread(cancel_python_env_reset)
        raise

    return SandboxRecreateResponse(status="accepted")
