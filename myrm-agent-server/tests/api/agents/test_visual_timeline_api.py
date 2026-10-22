"""API integration tests for Multi-Agent Visual Timeline & Cherry-Pick Rollback (Item 61).

[INPUT]
- app.api.agents.visual_timeline_router.router
- app.services.agent.visual_timeline_service.get_visual_timeline_service

[OUTPUT]
- Pytest test cases validating chronological timeline recording,
  multi-dimensional filtering, and surgical cherry-pick rollback without data loss.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_visual_timeline_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.visual_timeline_router import router as visual_timeline_router
from app.services.agent.visual_timeline_service import (
    VisualTimelineService,
    get_visual_timeline_service,
)


@pytest.fixture
def service() -> VisualTimelineService:
    """Isolated VisualTimelineService fixture with fresh journal and engine."""
    srv = VisualTimelineService()
    srv.clear()
    return srv


@pytest.fixture
def client(service: VisualTimelineService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected VisualTimelineService dependency."""
    app = FastAPI()
    app.include_router(visual_timeline_router)
    app.dependency_overrides[get_visual_timeline_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_record_and_get_timeline_node_api(client: TestClient) -> None:
    """Test recording an action node onto the visual timeline and retrieving it."""
    # 1. Record node
    payload = {
        "session_id": "sess-test-01",
        "actor_id": "agent-worker-1",
        "actor_name": "Worker Alpha",
        "actor_type": "local_agent",
        "operation_type": "file_modify",
        "file_path": "src/config.py",
        "line_start": 10,
        "line_end": 10,
        "before_content": "# DB configuration",
        "after_content": "DB_TIMEOUT = 30",
        "diff_summary": "Add database timeout parameter",
        "metadata": {"domain": "database"},
    }
    post_resp = client.post("/agents/visual-timeline/nodes", json=payload)
    assert post_resp.status_code == 200
    res_data = post_resp.json()["data"]
    node_id = res_data["node_id"]
    assert res_data["session_id"] == "sess-test-01"
    assert res_data["actor_name"] == "Worker Alpha"
    assert not res_data["is_rolled_back"]
    assert res_data["diff_summary"] == "Add database timeout parameter"

    # 2. Get node by ID
    get_resp = client.get(f"/agents/visual-timeline/nodes/{node_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()["data"]
    assert fetched["node_id"] == node_id
    assert fetched["diff_summary"] == "Add database timeout parameter"
    assert fetched["metadata"]["domain"] == "database"

    # 3. Non-existent node returns 404
    missing_resp = client.get("/agents/visual-timeline/nodes/non-existent-id")
    assert missing_resp.status_code == 404


def test_query_timeline_nodes_with_filters_api(client: TestClient) -> None:
    """Test querying timeline nodes matching multi-dimensional filters."""
    # Insert 3 nodes across different actors and operations
    nodes_data = [
        {
            "session_id": "sess-filter",
            "actor_id": "human-01",
            "actor_name": "Bob",
            "actor_type": "human_user",
            "operation_type": "file_create",
            "file_path": "README.md",
            "diff_summary": "Initial readme",
        },
        {
            "session_id": "sess-filter",
            "actor_id": "agent-01",
            "actor_name": "Coder",
            "actor_type": "local_agent",
            "operation_type": "file_modify",
            "file_path": "main.py",
            "diff_summary": "Setup server",
        },
        {
            "session_id": "sess-other",
            "actor_id": "agent-02",
            "actor_name": "Tester",
            "actor_type": "local_agent",
            "operation_type": "tool_execution",
            "file_path": "",
            "diff_summary": "Run tests",
        },
    ]
    for n in nodes_data:
        client.post("/agents/visual-timeline/nodes", json=n)

    # Query 1: Filter by session_id
    q1 = client.post(
        "/agents/visual-timeline/nodes/query",
        json={"session_id": "sess-filter"},
    )
    assert q1.status_code == 200
    nodes1 = q1.json()["data"]
    assert len(nodes1) == 2

    # Query 2: Filter by actor_type
    q2 = client.post(
        "/agents/visual-timeline/nodes/query",
        json={"session_id": "sess-filter", "actor_type": "human_user"},
    )
    assert q2.status_code == 200
    nodes2 = q2.json()["data"]
    assert len(nodes2) == 1
    assert nodes2[0]["actor_name"] == "Bob"

    # Query 3: Filter by file_path
    q3 = client.post(
        "/agents/visual-timeline/nodes/query",
        json={"session_id": "sess-filter", "file_path": "main.py"},
    )
    assert q3.status_code == 200
    nodes3 = q3.json()["data"]
    assert len(nodes3) == 1
    assert nodes3[0]["actor_name"] == "Coder"


def test_cherry_pick_rollback_success_api(
    client: TestClient,
    service: VisualTimelineService,
) -> None:
    """Test non-destructive surgical cherry-pick rollback via REST API."""
    file_path = "services/order.py"
    base_content = "def create_order():\n    pass\n"
    service.set_file_content(file_path, base_content)

    # 1. Agent A records a buggy change
    resp_a = client.post(
        "/agents/visual-timeline/nodes",
        json={
            "session_id": "sess-cherry",
            "actor_id": "agent-a",
            "actor_name": "Agent A",
            "actor_type": "local_agent",
            "operation_type": "file_modify",
            "file_path": file_path,
            "diff_summary": "Introduce bad tax rate",
            "before_content": base_content,
            "after_content": base_content + "TAX_RATE = -1.0\n",
            "line_start": 3,
            "line_end": 3,
        },
    )
    node_a_id = resp_a.json()["data"]["node_id"]
    service.set_file_content(file_path, base_content + "TAX_RATE = -1.0\n")

    # 2. Agent B records an unrelated valid change in another section
    content_with_bug = base_content + "TAX_RATE = -1.0\n"
    content_with_both = content_with_bug + "CURRENCY = 'USD'\n"
    client.post(
        "/agents/visual-timeline/nodes",
        json={
            "session_id": "sess-cherry",
            "actor_id": "agent-b",
            "actor_name": "Agent B",
            "actor_type": "local_agent",
            "operation_type": "file_modify",
            "file_path": file_path,
            "diff_summary": "Add currency constant",
            "before_content": content_with_bug,
            "after_content": content_with_both,
            "line_start": 4,
            "line_end": 4,
        },
    )
    service.set_file_content(file_path, content_with_both)

    # 3. Perform surgical cherry-pick rollback on Agent A's node only
    rb_resp = client.post(f"/agents/visual-timeline/nodes/{node_a_id}/rollback")
    assert rb_resp.status_code == 200
    rb_data = rb_resp.json()["data"]
    assert rb_data["status"] == "success"
    assert rb_data["node_id"] == node_a_id

    # Verify content in engine: Agent A's bug removed, Agent B's work preserved!
    final_content = service.get_file_content(file_path)
    assert "TAX_RATE = -1.0" not in final_content
    assert "CURRENCY = 'USD'" in final_content

    # 4. Repeating rollback on already rolled back node
    rb_again = client.post(f"/agents/visual-timeline/nodes/{node_a_id}/rollback")
    assert rb_again.status_code == 200
    assert rb_again.json()["data"]["status"] == "already_rolled_back"


def test_cherry_pick_rollback_conflict_api(
    client: TestClient,
    service: VisualTimelineService,
) -> None:
    """Test overlapping edits trigger conflict detection and prevent corrupted rollbacks."""
    file_path = "services/payment.py"
    service.set_file_content(file_path, "KEY = 'OLD'\n")

    # Node 1: modifies lines 1-2
    resp1 = client.post(
        "/agents/visual-timeline/nodes",
        json={
            "session_id": "sess-conflict-api",
            "actor_id": "agent-1",
            "actor_name": "Agent 1",
            "actor_type": "local_agent",
            "operation_type": "file_modify",
            "file_path": file_path,
            "diff_summary": "First edit",
            "before_content": "KEY = 'OLD'\n",
            "after_content": "KEY = 'MODIFIED'\n",
            "line_start": 1,
            "line_end": 2,
        },
    )
    node1_id = resp1.json()["data"]["node_id"]

    # Node 2: overlaps on line 2-3
    client.post(
        "/agents/visual-timeline/nodes",
        json={
            "session_id": "sess-conflict-api",
            "actor_id": "agent-2",
            "actor_name": "Agent 2",
            "actor_type": "local_agent",
            "operation_type": "file_modify",
            "file_path": file_path,
            "diff_summary": "Conflicting second edit",
            "before_content": "KEY = 'MODIFIED'\n",
            "after_content": "KEY = 'CONFLICT'\n",
            "line_start": 2,
            "line_end": 3,
        },
    )

    # Attempt to rollback node 1
    rb_resp = client.post(f"/agents/visual-timeline/nodes/{node1_id}/rollback")
    assert rb_resp.status_code == 200
    rb_data = rb_resp.json()["data"]
    assert rb_data["status"] == "conflict_detected"
    assert "modified overlapping lines" in rb_data["conflict_reason"]
