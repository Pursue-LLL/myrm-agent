"""WebUI desktop-control HTTP routes: OS permission probe, inspector snapshots, approvals, trust list, envelope.

[INPUT]
- myrm_agent_harness.toolkits.computer_use (POS: desktop session, permission probe, app identity)
- myrm_agent_harness.api.security (POS: screen lock / sleep detector)
- app.ai_agents.desktop_control (POS: approval registry, control gate, trust store)
- app.services.agent.gateway (POS: active desktop session lookup)

[OUTPUT]
- router: APIRouter mounted by ``router.py`` under ``/webui/desktop``

[POS]
Local-mode desktop panel API consumed by the Desktop Inspector and approval overlay. Handlers import the
harness and desktop-control modules lazily so the server starts without the computer-use extras. The
``/approval/test-seed`` route is hidden from OpenAPI and answers 404 outside local mode.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desktop")


@router.get("/permissions")
async def get_desktop_permissions(probe_capture: bool = False) -> JSONResponse:
    """Probe OS-level permissions required for desktop CU (Accessibility, Screen Recording).

    When ``probe_capture`` is true, also runs a functional capture sample
    (may briefly invoke the OS screenshot path). Default is grant-only.

    Returns per-capability booleans, optional capturable result, platform name,
    and deep-link URLs to the OS settings page where the user can grant access.
    Does NOT require an active desktop session — creates a temporary backend probe.
    """
    session = None
    try:
        from myrm_agent_harness.api.security import (
            ScreenLockState,
            get_default_screen_detector,
        )
        from myrm_agent_harness.toolkits.computer_use.session import (
            create_computer_session,
        )

        session = create_computer_session()
        status = await session.check_permissions(probe_capture=probe_capture)
        detector = get_default_screen_detector()
        screen_state = detector.get_state()
        return JSONResponse(
            content={
                "accessibility": status.accessibility,
                "screen_recording": status.screen_recording,
                "screen_recording_capturable": status.screen_recording_capturable,
                "post_event_access": status.post_event_access,
                "all_granted": status.all_granted,
                "capture_ready": status.capture_ready,
                "platform": status.platform,
                "settings_deeplinks": status.settings_deeplinks,
                "screen_locked": screen_state in (ScreenLockState.LOCKED, ScreenLockState.SLEEPING),
                "screen_sleeping": screen_state == ScreenLockState.SLEEPING,
            }
        )
    except Exception as e:
        logger.error("Desktop permissions check failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "permissions_check_failed",
                "message": "Desktop permissions check failed",
            },
        )
    finally:
        if session is not None:
            await session.close()


@router.get("/screen-lock/status")
async def get_desktop_screen_lock_status() -> JSONResponse:
    """Query current desktop physical lock and display sleep status."""
    from myrm_agent_harness.api.security import (
        ScreenLockState,
        get_default_screen_detector,
    )

    detector = get_default_screen_detector()
    state = detector.get_state()
    return JSONResponse(
        content={
            "locked": state in (ScreenLockState.LOCKED, ScreenLockState.SLEEPING),
            "state": state.value,
            "is_headless": detector.is_headless,
        }
    )


async def _ephemeral_foreground_desktop_snapshot() -> dict[str, object] | None:
    """Foreground AX capture without an active agent session (E2E dref fallback only)."""
    import platform

    if platform.system() != "Darwin":
        return None
    try:
        from myrm_agent_harness.toolkits.computer_use.backends.macos import MacOSBackend
        from myrm_agent_harness.toolkits.computer_use.desktop_session import (
            DesktopSession,
        )
        from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig

        backend = MacOSBackend()
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        payload = await session.export_inspector_snapshot()
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        logger.warning("Ephemeral foreground desktop snapshot failed: %s", exc)
    return None


@router.get("/snapshot")
async def get_desktop_snapshot(
    source: str = "live",
    chat_id: str | None = None,
) -> JSONResponse:
    """Get desktop snapshot for the Desktop Inspector panel.

    ``source=live`` (default) re-captures foreground AX; ``source=registry`` reads the
    last agent snapshot from DRefRegistry without re-capturing (E2E / approval overlay).
    ``source=foreground_e2e`` captures foreground AX without an active agent session (E2E only).
    Optional ``chat_id`` scopes registry/live lookup to a specific chat session.
    """
    from app.services.agent.gateway import get_agent_gateway

    normalized_source = source.strip().lower()
    if normalized_source == "foreground_e2e":
        payload = await _ephemeral_foreground_desktop_snapshot()
        if payload is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "foreground_e2e_unavailable",
                    "message": "Ephemeral foreground desktop snapshot unavailable",
                },
            )
        return JSONResponse(content=payload)

    gateway = get_agent_gateway()
    scoped_chat_id = chat_id.strip() if chat_id else None
    session = gateway.get_active_desktop_session(scoped_chat_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "no_active_desktop",
                "message": "No active desktop session",
            },
        )

    try:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import (
            DesktopSession,
        )

        if not isinstance(session, DesktopSession):
            return JSONResponse(
                status_code=404,
                content={
                    "error": "invalid_session",
                    "message": "Desktop session type mismatch",
                },
            )

        if normalized_source == "registry":
            payload = session.export_registry_view()
            if payload is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "no_registry_snapshot",
                        "message": "No snapshot refs in active desktop session registry",
                    },
                )
            return JSONResponse(content=payload)

        payload = await session.export_inspector_snapshot()
        return JSONResponse(content=payload)
    except Exception as e:
        logger.error("Desktop snapshot failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "snapshot_failed", "message": "Desktop snapshot failed"},
        )


@router.post("/approval/reset-runtime")
async def reset_desktop_approval_runtime() -> JSONResponse:
    """Reset in-memory desktop approval caches (E2E/dev recovery)."""
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    DesktopControlGate.reset_all_runtime_approval_state()
    return JSONResponse(content={"ok": True})


@router.get("/trust/apps")
async def list_desktop_trusted_apps() -> JSONResponse:
    """List always-trusted desktop applications for the current workspace."""
    from app.ai_agents.desktop_control.trust_store import list_trusted_desktop_apps
    from app.platform_utils.workspace_root import get_workspace_root

    apps = list_trusted_desktop_apps(workspace_root=str(get_workspace_root()))
    return JSONResponse(content={"apps": apps})


class DesktopTrustRevokeBody(BaseModel):
    trust_key: str


@router.delete("/trust/apps")
async def revoke_desktop_trusted_app(body: DesktopTrustRevokeBody) -> JSONResponse:
    """Revoke always-trusted status for a desktop application."""
    from app.ai_agents.desktop_control.trust_store import revoke_trusted_desktop_app
    from app.platform_utils.workspace_root import get_workspace_root

    revoked = revoke_trusted_desktop_app(
        workspace_root=str(get_workspace_root()),
        trust_key=body.trust_key,
    )
    if not revoked:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Trusted app not found"},
        )
    return JSONResponse(content={"ok": True})


@router.get("/approval/pending")
async def list_pending_desktop_approvals() -> JSONResponse:
    """List pending desktop approval request ids (E2E diagnostics).

    The `pending` id list and `count` shape is frozen for E2E helpers;
    `details` and `decisions` are additive diagnostics.
    """
    from app.ai_agents.desktop_control.registry import DesktopApprovalRegistry

    pending_ids = DesktopApprovalRegistry.pending_snapshot()
    return JSONResponse(
        content={
            "pending": pending_ids,
            "count": len(pending_ids),
            "details": DesktopApprovalRegistry.pending_details(),
            "decisions": DesktopApprovalRegistry.decision_snapshot(),
        }
    )


class DesktopApprovalResolveBody(BaseModel):
    request_id: str
    granted: bool
    scope: str = "once"
    reason: str = ""


@router.post("/approval/resolve")
async def resolve_desktop_approval(body: DesktopApprovalResolveBody) -> JSONResponse:
    """Resolve a pending desktop control approval request from the Web UI."""
    from app.ai_agents.desktop_control.registry import resolve_desktop_control_approval_status

    status = resolve_desktop_control_approval_status(
        body.request_id,
        granted=body.granted,
        scope=body.scope,
        reason=body.reason,
    )
    if status == "resolved":
        return JSONResponse(content={"ok": True})
    if status == "expired":
        return JSONResponse(
            status_code=410,
            content={
                "error": "expired",
                "message": "Approval request already settled (timeout); the agent run moved on",
            },
        )
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": "Approval request not found or already resolved",
        },
    )


class DesktopEnvelopePauseBody(BaseModel):
    task_id: str = ""


@router.post("/envelope/pause")
async def pause_desktop_envelope(body: DesktopEnvelopePauseBody | None = None) -> JSONResponse:
    """Emergency pause: immediately revoke active desktop intent envelope."""
    import asyncio

    from app.ai_agents.desktop_control.gate import DesktopControlGate

    task_id = (body.task_id if body else "").strip()
    paused = False
    for gate in list(DesktopControlGate._live_gates):
        if gate.envelope_manager.pause_envelope(task_id or None):
            paused = True
            asyncio.create_task(gate.envelope_manager.emit_progress(task_id or None))
    return JSONResponse(content={"ok": True, "paused": paused})


@router.get("/envelope/status")
async def get_desktop_envelope_status(task_id: str = "") -> JSONResponse:
    """Query active envelope status (remaining budget, limits)."""
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    target_task_id = task_id.strip()
    for gate in list(DesktopControlGate._live_gates):
        spec = gate.envelope_manager.get_envelope(target_task_id or None)
        if spec is not None:
            return JSONResponse(
                content={
                    "active": True,
                    "task_id": spec.task_id,
                    "used_actions": spec.used_actions,
                    "max_actions": spec.max_actions,
                    "remaining_budget": spec.remaining_budget(),
                }
            )
    return JSONResponse(content={"active": False})


class DesktopApprovalTestSeedBody(BaseModel):
    app_name: str = "TextEdit"
    operation: str = "foreground_control"
    reason: str = "Allow Myrm to control TextEdit for this task?"
    window_title: str = ""
    app_id: str = ""
    require_app_approval: bool = True


@router.post("/approval/test-seed", include_in_schema=False)
async def seed_desktop_approval_for_test(
    body: DesktopApprovalTestSeedBody,
) -> JSONResponse:
    """Local dev/test only: seed an in-memory desktop approval request."""
    from myrm_agent_harness.toolkits.computer_use.app_identity import resolve_trust_key

    from app.ai_agents.desktop_control.registry import DesktopApprovalRegistry, approval_fingerprint
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    trust_key = resolve_trust_key(app_name=body.app_name, app_id=body.app_id) or ""
    request_id, _pending = DesktopApprovalRegistry.create(
        reason=body.reason,
        operation=body.operation,
        app_name=body.app_name,
        window_title=body.window_title,
        app_id=body.app_id,
        fingerprint=approval_fingerprint(operation=body.operation, trust_key=trust_key),
        test_only=True,
    )
    return JSONResponse(
        content={
            "ok": True,
            "request_id": request_id,
            "app_name": body.app_name,
            "operation": body.operation,
            "reason": body.reason,
            "window_title": body.window_title,
            "app_id": body.app_id,
            "require_app_approval": body.require_app_approval,
        }
    )
