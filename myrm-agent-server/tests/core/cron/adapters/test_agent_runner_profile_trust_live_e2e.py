"""Live cron run bound to a profile carrying trusted desktop apps (Lane-C).

Proves the resolver -> adapter -> gate-params chain with a real DB profile
and a real model: the run must succeed and the trust entries must resolve.
"""

from __future__ import annotations

import os

import httpx
import pytest
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.agent_runner import (
    AgentJobRunner,
    resolve_trusted_desktop_keys,
)

pytestmark = pytest.mark.e2e

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080")
_E2E_TIMEOUT = httpx.Timeout(10.0)


def _e2e_request(method: str, url: str, **kwargs: object) -> httpx.Response:
    with httpx.Client(trust_env=False, timeout=_E2E_TIMEOUT) as client:
        return client.request(method, url, **kwargs)


def _auth_headers() -> dict[str, str]:
    try:
        resp = _e2e_request(
            "POST",
            f"{BASE_URL}/api/v1/auth/login",
            json={
                "username": os.getenv("TEST_USERNAME", "test"),
                "password": os.getenv("TEST_PASSWORD", "test"),
            },
        )
    except (httpx.TimeoutException, httpx.ConnectError):
        return {}
    if resp.status_code == 200:
        token = resp.json().get("data", {}).get("access_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
    return {}


async def test_live_cron_run_with_profile_trust() -> None:
    headers = _auth_headers()
    create_resp = _e2e_request(
        "POST",
        f"{BASE_URL}/api/v1/user-agents",
        json={
            "name": "Trust Latch Profile E2E",
            "system_prompt": "You are a test agent.",
            "trusted_desktop_apps": [{"name": "SAP GUI"}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    agent_id = create_resp.json()["data"]["id"]
    try:
        from app.services.agent.profile.profile_resolver import (
            get_agent_profile_resolver,
        )

        resolved = await get_agent_profile_resolver().resolve(agent_id)
        assert resolved is not None
        assert resolved.trusted_desktop_apps == ({"name": "SAP GUI"},)
        assert resolve_trusted_desktop_keys(resolved.trusted_desktop_apps) == (
            "sap gui",
        )

        job = CronJob(  # type: ignore[arg-type]
            id="cron-trust-profile-ping",
            user_id="user-1",
            name="TrustProfilePing",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 2 * * *"),
            status=JobStatus.ACTIVE,
            prompt="Reply with exactly the word PONG and nothing else.",
            delivery=DeliveryConfig(channel="chat"),
            timeout_seconds=120,
            max_retries=0,
            agent_id=agent_id,
        )
        result = await AgentJobRunner().run(job)
        assert result.success, f"cron run failed: {result.error}"
        assert result.output is not None and "PONG" in result.output
    finally:
        _e2e_request(
            "DELETE",
            f"{BASE_URL}/api/v1/user-agents/{agent_id}",
            headers=headers,
        )
