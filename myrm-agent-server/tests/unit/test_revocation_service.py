"""Unit tests for Server RevocationService and SSE broadcast integration.

[POS]
Validates that revocation of credentials, agents, resources, or sessions
triggers immediate termination in TaskLeaseGovernor and broadcasts real-time SSE events.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.security.lease import TaskLeaseGovernor

from app.services.event.app_event_bus import AppEventType, get_event_bus
from app.services.security.revocation_service import RevocationService


@pytest.fixture(autouse=True)
def reset_governor_fixture() -> None:
    """Reset TaskLeaseGovernor singleton between test runs."""
    TaskLeaseGovernor.reset_instance()
    RevocationService.set_governor(None)


@pytest.mark.asyncio
async def test_revoke_credential_terminates_in_flight_tasks_and_emits_event() -> None:
    """Ensure revoke_credential terminates in-flight task holding it and publishes SSE broadcast."""
    governor = TaskLeaseGovernor.get_instance()
    task_id = "task-flight-01"
    credential_id = "cred-vault-007"

    governor.acquire_lease(task_id=task_id, bound_resources={credential_id}, ttl_seconds=30.0)

    # In-flight task
    async def dummy_work() -> None:
        await asyncio.sleep(10.0)

    loop_task = asyncio.create_task(dummy_work())
    governor.register_task(task_id=task_id, asyncio_task=loop_task)

    bus = get_event_bus()
    mock_publish = MagicMock()
    with patch.object(bus, "publish", mock_publish):
        terminated_count = await RevocationService.revoke_credential(
            credential_id=credential_id,
            reason="Compromised token",
        )

        assert terminated_count == 1
        assert loop_task.cancelled() or loop_task.cancelling() > 0

        # Verify SSE event was published
        published_events = [
            call[0][0]
            for call in mock_publish.call_args_list
            if call[0][0].event_type == AppEventType.REVOCATION_BROADCAST
        ]
        assert len(published_events) == 1
        event_data = published_events[0].data
        assert event_data["subject_type"] == "credential"
        assert event_data["subject_id"] == credential_id
        assert event_data["reason"] == "Compromised token"
        assert event_data["terminated_tasks_count"] == 1


@pytest.mark.asyncio
async def test_revoke_agent_and_resource_and_session() -> None:
    """Ensure agent, resource, and session revocations propagate correctly."""
    governor = TaskLeaseGovernor.get_instance()
    task_id = "task-flight-02"
    agent_id = "agent-rogue"
    resource_id = "resource:db_sensitive"

    governor.acquire_lease(
        task_id=task_id,
        bound_resources={agent_id, resource_id},
        ttl_seconds=30.0,
    )

    terminated_res = await RevocationService.revoke_resource(
        resource_id=resource_id,
        reason="Admin revoked db access",
    )
    assert terminated_res == 1

    # Revoking again should terminate 0 tasks as lease is already purged
    terminated_again = await RevocationService.revoke_agent(
        agent_id=agent_id,
        reason="Agent retired",
    )
    assert terminated_again == 0

    # Session revocation with no active tasks
    terminated_session = await RevocationService.revoke_session(
        session_id="session-unknown",
        reason="E-Stop triggered",
    )
    assert terminated_session == 0
