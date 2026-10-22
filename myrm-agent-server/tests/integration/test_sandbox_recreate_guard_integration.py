"""Integration: a manual sandbox recreate refuses while it would kill running work; otherwise it asks the control plane."""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from myrm_agent_harness.agent.meta_tools.bash._background.session_spawn_lifecycle import (
    reset_spawn_lifecycle_for_tests,
)
from myrm_agent_harness.api.hooks import (
    get_background_registry,
    set_global_background_job_finish_handler,
)

from app.core.agent.run_activity import track_background_agent_run
from app.services.agent.background_job.background_job_finish_handler import (
    ServerBackgroundJobFinishHandler,
)
from app.services.agent.gateway import AgentGateway, GatewayConfig
from tests.integration.test_background_tasks_rest_api import _spawn_background

_RUN_ACTIVITY_REGISTRY = "app.core.agent.run_activity.ACTIVE_SUBAGENTS"
_ROUTER = "app.api.system.sandbox_recreate"


def _build_system_app() -> FastAPI:
    from app.api.system.router import router as system_router

    app = FastAPI()
    app.include_router(system_router, prefix="/api/v1/system")
    return app


@pytest.fixture(autouse=True)
def _clear_registry() -> Iterator[None]:
    registry = get_background_registry()
    registry._entries.clear()
    reset_spawn_lifecycle_for_tests()
    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())
    yield
    registry._entries.clear()
    reset_spawn_lifecycle_for_tests()
    set_global_background_job_finish_handler(None)


@pytest.fixture
def gateway() -> Iterator[MagicMock]:
    """An agent gateway with nothing running and no sub-agent task alive."""
    stub = MagicMock()
    stub.active_session_ids.return_value = frozenset()
    stub.active_count = 0
    with patch(f"{_ROUTER}.get_agent_gateway", return_value=stub), patch(_RUN_ACTIVITY_REGISTRY, {}):
        yield stub


_SANDBOX_ID = "sandbox-test"
_TOKEN = "token"


def _control_plane_reply(status_code: int) -> MagicMock:
    return MagicMock(status_code=status_code, text="{}")


async def _post_recreate(
    *,
    is_sandbox_instance: bool = True,
    sandbox_id: str = _SANDBOX_ID,
    token: str = _TOKEN,
    control_plane_outcome: MagicMock | BaseException | None = None,
    body: dict[str, bool] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Response, AsyncMock]:
    """POST the recreate route (with ``body`` as JSON when given); by default in a sandbox instance whose control plane accepts.

    Returns the reply and the control plane call.
    """
    caps = MagicMock(is_sandbox_instance=is_sandbox_instance)
    settings = MagicMock()
    settings.control_plane.effective_url.return_value = "http://cp.test"
    settings.control_plane.sandbox_id = sandbox_id
    settings.control_plane.telemetry_token.get_secret_value.return_value = token

    outcome = control_plane_outcome if control_plane_outcome is not None else _control_plane_reply(202)
    control_plane = MagicMock()
    control_plane.post = AsyncMock(side_effect=outcome) if isinstance(outcome, BaseException) else AsyncMock(return_value=outcome)
    control_plane.__aenter__ = AsyncMock(return_value=control_plane)
    control_plane.__aexit__ = AsyncMock(return_value=False)

    transport = ASGITransport(app=_build_system_app())
    with (
        patch(f"{_ROUTER}.get_deployment_capabilities", return_value=caps),
        patch(f"{_ROUTER}.get_settings", return_value=settings),
        patch(f"{_ROUTER}.httpx.AsyncClient", return_value=control_plane),
    ):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/system/sandbox/recreate", json=body, headers=headers)
    return response, control_plane.post


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refuses_while_background_shell_jobs_run(tmp_path: Path, gateway: MagicMock) -> None:
    await _spawn_background(
        tmp_path,
        chat_id=f"recreate-guard-{uuid.uuid4().hex[:12]}",
        command=f'{sys.executable} -c "import time; time.sleep(60)"',
        reason="recreate guard integration",
    )

    response, control_plane_call = await _post_recreate()

    assert response.status_code == 409
    assert "background shell job" in response.json()["detail"].lower()
    control_plane_call.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forwards_to_the_control_plane_when_nothing_is_running(gateway: MagicMock) -> None:
    response, control_plane_call = await _post_recreate()

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    control_plane_call.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_asks_the_control_plane_with_the_sandboxs_own_identity(gateway: MagicMock) -> None:
    """The control plane scopes the call by the token plus the sandbox id header; the id also names the target."""
    _, control_plane_call = await _post_recreate()

    control_plane_call.assert_awaited_once_with(
        f"http://cp.test/api/internal/sandboxes/{_SANDBOX_ID}/recreate",
        headers={"X-Telemetry-Token": _TOKEN, "X-Sandbox-Id": _SANDBOX_ID},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refuses_outside_sandbox_mode(gateway: MagicMock) -> None:
    response, control_plane_call = await _post_recreate(is_sandbox_instance=False)

    assert response.status_code == 403
    control_plane_call.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sandbox_id", "token"),
    [("", _TOKEN), (_SANDBOX_ID, "")],
    ids=["no-sandbox-id", "no-token"],
)
async def test_refuses_without_control_plane_credentials(gateway: MagicMock, sandbox_id: str, token: str) -> None:
    response, control_plane_call = await _post_recreate(sandbox_id=sandbox_id, token=token)

    assert response.status_code == 503
    control_plane_call.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [403, 500], ids=["token-rejected", "swap-failed"])
async def test_reports_a_control_plane_rejection_as_bad_gateway(gateway: MagicMock, status_code: int) -> None:
    response, _ = await _post_recreate(control_plane_outcome=_control_plane_reply(status_code))

    assert response.status_code == 502
    assert response.json()["detail"] == f"Control plane returned {status_code}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reports_an_unreachable_control_plane_as_bad_gateway(gateway: MagicMock) -> None:
    response, _ = await _post_recreate(control_plane_outcome=httpx.ConnectError("connection refused"))

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to reach control plane"


@contextmanager
def _chat_turn_reserved(gateway: MagicMock) -> Iterator[None]:
    gateway.active_session_ids.return_value = frozenset({"chat-1"})
    yield


@contextmanager
def _gateway_turn_without_session(gateway: MagicMock) -> Iterator[None]:
    gateway.active_count = 1
    yield


@contextmanager
def _gateway_less_run(gateway: MagicMock) -> Iterator[None]:
    """A cron, kanban, IM channel or eval run: it never passes through the gateway."""
    with track_background_agent_run():
        yield


@contextmanager
def _detached_subagent(gateway: MagicMock) -> Iterator[None]:
    with patch(_RUN_ACTIVITY_REGISTRY, {"task-1": MagicMock()}):
        yield


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arrange",
    [_chat_turn_reserved, _gateway_turn_without_session, _gateway_less_run, _detached_subagent],
    ids=["chat-turn", "gateway-turn-without-session", "gateway-less-run", "detached-subagent"],
)
async def test_refuses_while_an_agent_run_is_in_flight(
    gateway: MagicMock, arrange: Callable[[MagicMock], AbstractContextManager[None]]
) -> None:
    with arrange(gateway):
        response, control_plane_call = await _post_recreate()

    assert response.status_code == 409
    assert "agent run" in response.json()["detail"].lower()
    control_plane_call.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_real_gateway_session_blocks_until_it_is_released(gateway: MagicMock) -> None:
    """The stubs above only echo what the test tells them; this runs the gate against the real gateway API."""
    real_gateway = AgentGateway(GatewayConfig())
    real_gateway.reserve_session("chat-1")
    with patch(f"{_ROUTER}.get_agent_gateway", return_value=real_gateway):
        refused, _ = await _post_recreate()
        real_gateway.release_session("chat-1")
        accepted, control_plane_call = await _post_recreate()

    assert refused.status_code == 409
    assert accepted.status_code == 200
    control_plane_call.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_allowed_again_once_the_run_ends(gateway: MagicMock) -> None:
    with track_background_agent_run():
        refused, _ = await _post_recreate()
    accepted, control_plane_call = await _post_recreate()

    assert refused.status_code == 409
    assert accepted.status_code == 200
    control_plane_call.assert_awaited_once()


@pytest.fixture
def reset_marker(tmp_path: Path) -> Iterator[Path]:
    """The deferred Python-environment reset request, redirected away from the real data directory."""
    marker = tmp_path / "locks" / "python-env-reset"
    with patch("app.services.infra.python_env_reset._marker_path", return_value=marker):
        yield marker


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("body", [None, {}, {"reset_python_env": False}], ids=["no-body", "empty-body", "flag-off"])
async def test_a_plain_restart_leaves_the_python_environment_alone(
    gateway: MagicMock, reset_marker: Path, body: dict[str, bool] | None
) -> None:
    """The backup-restore restart calls this route without a body and must keep the user's installed packages."""
    response, _ = await _post_recreate(body=body)

    assert response.status_code == 200
    assert not reset_marker.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_restore_restart_sends_a_json_content_type_with_no_body(gateway: MagicMock, reset_marker: Path) -> None:
    """The frontend's API client always labels requests as JSON, even the body-less restart after a restore."""
    response, _ = await _post_recreate(headers={"Content-Type": "application/json"})

    assert response.status_code == 200
    assert not reset_marker.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_asking_for_a_reset_leaves_a_request_for_the_next_start(gateway: MagicMock, reset_marker: Path) -> None:
    response, control_plane_call = await _post_recreate(body={"reset_python_env": True})

    assert response.status_code == 200
    control_plane_call.assert_awaited_once()
    assert reset_marker.exists()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "control_plane_outcome",
    [_control_plane_reply(403), _control_plane_reply(500), httpx.ConnectError("connection refused")],
    ids=["token-rejected", "swap-failed", "unreachable"],
)
async def test_a_failed_swap_withdraws_the_reset_request(
    gateway: MagicMock, reset_marker: Path, control_plane_outcome: MagicMock | Exception
) -> None:
    """The user is told the reset failed, so a later restart must not clear their packages."""
    response, _ = await _post_recreate(control_plane_outcome=control_plane_outcome, body={"reset_python_env": True})

    assert response.status_code == 502
    assert not reset_marker.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_second_click_during_the_swap_does_not_withdraw_the_first_reset_request(
    gateway: MagicMock, reset_marker: Path
) -> None:
    """The old container keeps serving until the swap stops it; a repeated click is refused as already recreating."""
    first, _ = await _post_recreate(body={"reset_python_env": True})
    second, _ = await _post_recreate(control_plane_outcome=_control_plane_reply(409), body={"reset_python_env": True})

    assert first.status_code == 200
    assert second.status_code == 502
    assert reset_marker.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_cancelled_request_withdraws_the_reset_request(gateway: MagicMock, reset_marker: Path) -> None:
    """Whether the control plane accepted the swap is unknown, and a request left behind could clear packages later."""
    with pytest.raises(asyncio.CancelledError):
        await _post_recreate(control_plane_outcome=asyncio.CancelledError(), body={"reset_python_env": True})

    assert not reset_marker.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_refused_reset_never_leaves_a_request(gateway: MagicMock, reset_marker: Path) -> None:
    with _chat_turn_reserved(gateway):
        refused, _ = await _post_recreate(body={"reset_python_env": True})
    outside_sandbox, _ = await _post_recreate(is_sandbox_instance=False, body={"reset_python_env": True})

    assert refused.status_code == 409
    assert outside_sandbox.status_code == 403
    assert not reset_marker.exists()
