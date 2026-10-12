"""Unit tests for ActionGrantService in server."""

from __future__ import annotations

from app.services.security.action_grant_service import (
    ActionGrantService,
    get_action_grant_service,
)


def test_service_singleton_and_custom_instance() -> None:
    """Test singleton resolution and custom service instantiation."""
    s1 = get_action_grant_service()
    s2 = get_action_grant_service()
    assert s1 is s2

    custom = ActionGrantService(suggestion_threshold=5)
    assert custom.registry is not None
    assert custom.budget_engine is not None


def test_service_grant_lifecycle_and_evaluation() -> None:
    """Test creating grant and evaluating matching action through service."""
    service = ActionGrantService()
    grant = service.create_grant(
        agent_id="agent-writer",
        service="notion",
        action="update",
        transaction="doc_123",
        ttl_seconds=300,
        max_uses=1,
    )
    assert grant.grant_id.startswith("grant_")
    assert grant.used_count == 0

    # 1. First evaluation passes
    eval_res1, updated = service.evaluate_action(
        agent_id="agent-writer",
        service="notion",
        action="update",
        transaction="doc_123",
    )
    assert eval_res1.is_granted is True
    assert eval_res1.status == "granted"
    assert updated is not None
    assert updated.used_count == 1

    # 2. Second evaluation fails due to quota exhaustion
    eval_res2, _ = service.evaluate_action(
        agent_id="agent-writer",
        service="notion",
        action="update",
        transaction="doc_123",
    )
    assert eval_res2.is_granted is False
    assert eval_res2.status == "not_found"


def test_service_cascade_reclaim_and_revocation() -> None:
    """Test grant revocation and cascade reclamation in service."""
    service = ActionGrantService()
    g1 = service.create_grant("agent-x", "github", "create", "pr_1", 300)
    g2 = service.create_grant("agent-x", "github", "merge", "pr_1", 300)
    assert g1.grant_id != g2.grant_id

    # Revoke single
    assert service.revoke_grant(g1.grant_id, "User cancelled PR") is True
    assert service.revoke_grant(g1.grant_id) is False

    # Cascade reclaim by service
    revoked = service.cascade_reclaim(service="github", reason="GitHub app uninstalled")
    assert revoked == 1  # only g2 was still active

    active_grants = service.get_active_grants(agent_id="agent-x")
    assert len(active_grants) == 0


def test_service_trust_budget_workflow() -> None:
    """Test recording approvals, suggestion trigger, and demotion."""
    service = ActionGrantService(suggestion_threshold=2)

    # 1. Record first approval
    b1 = service.record_approval("agent-y", "feishu", "send")
    assert b1.consecutive_approvals == 1
    assert service.should_suggest_grant("agent-y", "feishu", "send") is False

    # 2. Record second approval hits threshold
    b2 = service.record_approval("agent-y", "feishu", "send")
    assert b2.consecutive_approvals == 2
    assert service.should_suggest_grant("agent-y", "feishu", "send") is True

    # 3. Demotion collapses trust to 0 and locks Ask
    demoted = service.record_demotion(
        "agent-y", "feishu", "send", reason="Spam message sent"
    )
    assert demoted.consecutive_approvals == 0
    assert demoted.is_locked_to_ask is True
    assert service.should_suggest_grant("agent-y", "feishu", "send") is False
