"""Tests for the PATCH /pending/{id}/revise endpoint.

Covers:
- Successful revision (scan passes)
- Revision with malicious content (scan fails)
- Revision of non-existent record (404)
- Revision of already-approved record (409 conflict)
- Revision with empty content (409 conflict)
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.main import app
from app.platform_utils import get_database_engine
from app.services.skills.evolution_reviews import EvolutionReviewRecord, create_evolution_review_record


@pytest.fixture(autouse=True)
async def ensure_tables() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def sample_pending_evolution() -> EvolutionReviewRecord:
    skill_path = f"/tmp/test_revise_skill_{uuid.uuid4().hex}.md"
    os.makedirs(os.path.dirname(skill_path), exist_ok=True)
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write("# Original\nHello world")
    record = await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id="revise_test_skill",
        skill_name="revise_skill",
        skill_path=skill_path,
        evolution_type="enhance",
        reason="Test revision flow",
        original_content="# Original\nHello world",
        evolved_content="# Enhanced\nHello world v2",
        confidence=0.7,
        test_passed=True,
        task_context="revise flow test",
    )
    yield record
    if os.path.exists(skill_path):
        os.remove(skill_path)
    bak_path = f"{skill_path}.bak"
    if os.path.exists(bak_path):
        os.remove(bak_path)


@pytest.mark.asyncio
async def test_revise_pending_evolution_success(
    async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord
) -> None:
    """Revision with safe content should succeed and keep PENDING_REVIEW status."""
    new_content = "# Revised\nHello world v3 - improved by human"
    response = await async_client.patch(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/revise",
        json={"evolved_content": new_content},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["skill_id"] == "revise_test_skill"
    assert body["test_passed"] is True
    assert body["reason_code"] == "revised"
    assert body["remediation"] is None

    async with get_session() as db:
        record = await db.get(ApprovalRecord, sample_pending_evolution.id)
        assert record is not None
        assert isinstance(record.payload, dict)
        assert record.payload["evolved_content"] == new_content
        assert record.payload["growth_status"] == "PENDING_REVIEW"


@pytest.mark.asyncio
async def test_revise_then_approve(
    async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord
) -> None:
    """After revision, the record should still be approvable and apply the revised content."""
    new_content = "# Final version\nApproved content"
    revise_resp = await async_client.patch(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/revise",
        json={"evolved_content": new_content},
    )
    assert revise_resp.status_code == 200

    approve_resp = await async_client.post(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/approve"
    )
    assert approve_resp.status_code == 200
    body = approve_resp.json()
    # Apply may succeed or fail depending on SkillStore availability in test env.
    # The key assertion is that the record transitions to either approved or apply_failed (not rejected/scan-failed).
    assert body["status"] in {"approved", "apply_failed"}
    if body["status"] == "approved":
        with open(sample_pending_evolution.skill_path, "r", encoding="utf-8") as f:
            written = f.read()
            assert "Final version" in written or "Approved content" in written


@pytest.mark.asyncio
async def test_revise_with_malicious_content(
    async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord
) -> None:
    """Content that triggers security scanner should move to FAILED_SCAN."""
    malicious_content = "import os\nos.system('rm -rf /')\n"
    response = await async_client.patch(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/revise",
        json={"evolved_content": malicious_content},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED_SCAN"
    assert body["test_passed"] is False
    assert body["reason_code"] == "revised_failed_scan"
    assert body["remediation"] is not None


@pytest.mark.asyncio
async def test_revise_nonexistent_record(async_client: AsyncClient) -> None:
    """Revising a non-existent record should return 404."""
    response = await async_client.patch(
        "/api/v1/evolution/pending/nonexistent-id-12345/revise",
        json={"evolved_content": "anything"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revise_already_approved_record(
    async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord
) -> None:
    """Revising an already-approved+applied record should return 409.
    
    Note: if approve results in APPLY_FAILED, revise is still allowed (by design).
    We test the truly APPROVED path by checking DB state after approve.
    """
    approve_resp = await async_client.post(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/approve"
    )
    assert approve_resp.status_code == 200
    approve_body = approve_resp.json()

    response = await async_client.patch(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/revise",
        json={"evolved_content": "too late to revise"},
    )
    if approve_body["status"] == "approved":
        # Fully approved+applied -> revise should be rejected
        assert response.status_code == 409
    else:
        # apply_failed -> revise allowed (user can fix and retry)
        assert response.status_code == 200
        assert response.json()["status"] in {"PENDING_REVIEW", "FAILED_SCAN"}


@pytest.mark.asyncio
async def test_revise_with_empty_content(
    async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord
) -> None:
    """Empty content should be rejected with 409."""
    response = await async_client.patch(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/revise",
        json={"evolved_content": "   "},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_revise_preserves_audit_trail(
    async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord
) -> None:
    """Revision should create an experience ledger event."""
    new_content = "# Audited revision"
    response = await async_client.patch(
        f"/api/v1/evolution/pending/{sample_pending_evolution.id}/revise",
        json={"evolved_content": new_content},
    )
    assert response.status_code == 200

    async with get_session() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(ExperienceLedgerEvent).where(
                ExperienceLedgerEvent.entity_id == sample_pending_evolution.id
            )
        )
        events = list(result.scalars().all())
        revision_events = [e for e in events if e.outcome == "revised"]
        assert len(revision_events) >= 1
