"""Verify stream orchestrator wires harness ApprovalTimeoutScheduler (no API fixtures)."""


def test_agent_stream_resume_can_cancel_approval_timeout() -> None:
    from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

    from app.services.agent.stream_session import orchestrator

    assert orchestrator.ApprovalTimeoutScheduler is ApprovalTimeoutScheduler
