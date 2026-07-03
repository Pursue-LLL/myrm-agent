"""External agent subscription-auth endpoints.

GUI/SaaS-driven authentication for delegated CLI agents (Codex / Claude Code /
Gemini / Qwen): query login status for badges, drive an interactive login over
SSE (surfacing the login URL / device code), feed a pasted code, import a
credential captured elsewhere, or log out. Mounted globally (local + SaaS) since
subscription auth is an agent-config concern, not channel management.

[INPUT]
- myrm_agent_harness.toolkits.acp.auth (POS: ACP subscription auth subsystem)
- myrm_agent_harness.toolkits.acp.backend_detector::BackendDetector (POS: CLI backend detection)

[OUTPUT]
- router: external agent auth endpoints under /external-agents

[POS]
外部 Agent 订阅鉴权 HTTP API 层。让 GUI/SaaS 用户用自有订阅驱动外部 CLI。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class ExternalAgentLoginRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Executable command or path of the CLI")
    backend: str | None = Field(default=None, description="Backend key; inferred from command if omitted")
    session_id: str = Field(..., alias="sessionId", min_length=1, max_length=128)
    timeout_seconds: int = Field(default=300, alias="timeoutSeconds", ge=30, le=1800)

    class Config:
        populate_by_name = True


class ExternalAgentFeedRequest(BaseModel):
    text: str = Field(..., description="Line fed to the login process stdin (e.g. a pasted auth code)")


class ExternalAgentImportRequest(BaseModel):
    backend: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    filename: str | None = Field(default=None)


class ExternalAgentLogoutRequest(BaseModel):
    backend: str = Field(..., min_length=1)


class _LoginRegistry:
    """Tracks in-flight login sessions so a feed/cancel can reach a live process."""

    def __init__(self) -> None:
        self._sessions: dict[str, object] = {}

    def add(self, session_id: str, session: object) -> None:
        self._sessions[session_id] = session

    def get(self, session_id: str) -> object | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


_login_registry = _LoginRegistry()


@router.get("/auth/status")
async def external_agent_auth_status() -> dict[str, object]:
    """Report install + login state for every known backend (drives status badges)."""
    from app.ai_agents.general_agent.external_agents import get_aggregate_health_metrics
    from myrm_agent_harness.toolkits.acp.auth import CredentialStore, known_backends, profile_for
    from myrm_agent_harness.toolkits.acp.backend_detector import BackendDetector

    detector = BackendDetector()
    detected = {b.name: b for b in await detector.detect()}
    store = CredentialStore()
    health_by_backend = get_aggregate_health_metrics()

    backends: list[dict[str, object]] = []
    for name in known_backends():
        profile = profile_for(name)
        if profile is None:
            continue
        found = detected.get(name)
        state = store.state(name)
        health = health_by_backend.get(name)
        entry: dict[str, object] = {
            "backend": name,
            "installed": found is not None,
            "path": found.path if found else None,
            "version": found.version if found else None,
            "authenticated": state.authenticated,
            "authStatus": state.status.value,
            "loginStrategy": profile.login_strategy.value,
            "scriptableLogin": profile.scriptable_login,
            "needsCodeInput": profile.needs_code_input,
        }
        if health is not None:
            entry["healthMetrics"] = health
        backends.append(entry)
    return {"backends": backends}


@router.post("/install/{backend}")
async def external_agent_install(backend: str) -> StreamingResponse:
    """Install an external agent CLI into the isolated toolchain."""
    from myrm_agent_harness.toolkits.acp.toolchains import IsolatedToolchainManager

    manager = IsolatedToolchainManager()

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for msg in manager.install_backend(backend):
                payload = {"type": "progress", "message": msg}
                yield f"data: {json.dumps(payload)}\n\n"

            # After installation, force detector cache invalidation
            from myrm_agent_harness.toolkits.acp.backend_detector import BackendDetector

            detector = BackendDetector()
            detector.invalidate_cache()

            yield f"data: {json.dumps({'type': 'success', 'message': 'Installation complete'})}\n\n"
        except Exception as exc:
            logger.error("Installation failed", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/auth/login")
async def external_agent_auth_login(body: ExternalAgentLoginRequest) -> StreamingResponse:
    """Drive an interactive CLI login, streaming progress events as SSE."""
    from myrm_agent_harness.toolkits.acp.auth import CliLoginSession, profile_for

    profile = profile_for(body.backend or body.command)
    if profile is None:
        raise HTTPException(status_code=400, detail=f"Unknown external agent backend: {body.backend or body.command}")

    session = CliLoginSession(body.command, profile, timeout_seconds=body.timeout_seconds)
    _login_registry.add(body.session_id, session)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in session.run():
                payload: dict[str, object] = {"type": event.type.value, "message": event.message}
                if event.url:
                    payload["url"] = event.url
                if event.code:
                    payload["code"] = event.code
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as exc:  # pragma: no cover - defensive: never leak a raw 500 into the stream
            logger.warning("external_agent_login_stream_error backend=%s error=%s", profile.backend, exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            await session.cancel()
            _login_registry.remove(body.session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/auth/login/{session_id}/feed")
async def external_agent_auth_feed(session_id: str, body: ExternalAgentFeedRequest) -> dict[str, bool]:
    """Forward a user-supplied line (e.g. a pasted auth code) to a live login session."""
    from myrm_agent_harness.toolkits.acp.auth import CliLoginSession

    session = _login_registry.get(session_id)
    if not isinstance(session, CliLoginSession):
        raise HTTPException(status_code=404, detail="No active login session")
    await session.feed(body.text)
    return {"ok": True}


@router.post("/auth/import")
async def external_agent_auth_import(body: ExternalAgentImportRequest) -> dict[str, object]:
    """Persist a credential blob captured on another machine (universal fallback)."""
    from myrm_agent_harness.toolkits.acp.auth import CredentialStore

    store = CredentialStore()
    try:
        state = store.import_credential(body.backend, body.content, filename=body.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"backend": state.backend, "authenticated": state.authenticated, "authStatus": state.status.value}


@router.post("/auth/logout")
async def external_agent_auth_logout(body: ExternalAgentLogoutRequest) -> dict[str, object]:
    """Remove a backend's stored subscription credentials."""
    from myrm_agent_harness.toolkits.acp.auth import CredentialStore

    store = CredentialStore()
    try:
        state = store.clear(body.backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"backend": state.backend, "authenticated": state.authenticated, "authStatus": state.status.value}
