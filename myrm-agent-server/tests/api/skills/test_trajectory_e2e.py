import json
import uuid

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
)

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.skills.evolution_reviews import EVOLUTION_ACTION_TYPE


@pytest.mark.asyncio
async def test_trajectory_end_to_end_flow(client: TestClient):
    """
    Integration test for the end-to-end flow of trajectory analysis:
    1. Create a mock EvolutionProposal with a trajectory
    2. Pass it through ConfidenceApprovalFlow
    3. Verify it's saved in the database correctly
    4. Fetch it via the pending API and verify trajectory is exposed
    """

    # 1. Create a mock proposal with trajectory
    skill_id = f"test_skill_{uuid.uuid4().hex[:8]}"
    trajectory_markdown = (
        "## 会话概览\n- 会话 ID: test_session\n\n## 根因分析\n**失败模式**: `timeout`"
    )

    proposal = EvolutionProposal(
        skill_id=skill_id,
        evolution_type=EvolutionType.FIX,
        original_content="def old(): pass",
        proposed_content="def new(): pass",
        diff="--- old\n+++ new",
        score=0.4,  # Force manual review
        reasoning="Fixing timeout issue",
        task_context="User reported timeout",
        trajectory=trajectory_markdown,
        is_general=True,
    )

    # 2. Process through ConfidenceApprovalFlow
    flow = ConfidenceApprovalFlow(auto_approve_threshold=0.8)
    result = await flow.process_evolution(proposal)

    assert result.approved is False
    assert result.requires_manual_review is True

    # 3. Verify in database
    async with get_session() as db:
        from sqlalchemy import desc, select

        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
            .order_by(desc(ApprovalRecord.created_at))
            .limit(1)
        )
        db_result = await db.execute(stmt)
        record = db_result.scalars().first()

        assert record is not None
        payload = record.payload
        if isinstance(payload, str):
            payload = json.loads(payload)

        assert payload.get("skill_id") == skill_id
        assert payload.get("trajectory") == trajectory_markdown

    # 4. Fetch via API
    response = client.get("/api/v1/evolution/pending")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data

    # Find our specific item
    found_item = None
    for item in data["items"]:
        if item.get("skill_id") == skill_id:
            found_item = item
            break

    assert found_item is not None
    assert found_item.get("trajectory") == trajectory_markdown

    # 5. Fetch via Growth API
    response = client.get("/api/v1/skill-growth/cases")
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    assert "items" in data["data"]

    # Find our specific item
    found_item_growth = None
    for item in data["data"]["items"]:
        if item.get("skill_id") == skill_id:
            found_item_growth = item
            break

    assert found_item_growth is not None
    assert found_item_growth.get("trajectory") == trajectory_markdown
