"""Unit tests for Multi-Agent Debate Workroom & Kanban Integration API endpoints.

[INPUT]
- app.api.agents.debate_workroom_router.router
- app.services.agent.debate_workroom_service.DebateWorkroomService

[OUTPUT]
- Pytest test cases verifying room creation, leader decomposition, specialist arguments,
  anti-wheel-war guard, phase advance, consensus convergence, and Kanban synchronization.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_debate_workroom_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.debate_workroom_router import (
    get_debate_workroom_service,
)
from app.api.agents.debate_workroom_router import (
    router as debate_workroom_router,
)
from app.services.agent.debate_workroom_service import DebateWorkroomService


@pytest.fixture
def mock_debate_service() -> DebateWorkroomService:
    return DebateWorkroomService()


@pytest.fixture
def debate_client(
    mock_debate_service: DebateWorkroomService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(debate_workroom_router)
    app.dependency_overrides[get_debate_workroom_service] = lambda: mock_debate_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_debate_room_lifecycle_and_decomposition(debate_client: TestClient) -> None:
    chat_id = "chat-debate-001"

    # 1. Create debate room
    create_payload = {
        "room_id": "room-ws-test",
        "topic": "Migrate core ledger to distributed raft consensus",
        "leader_agent_id": "agent-lead",
        "participants": [
            {"agent_id": "agent-lead", "name": "Lead Arch", "role": "leader"},
            {"agent_id": "agent-critic", "name": "Sec Auditor", "role": "critic"},
            {"agent_id": "agent-coder", "name": "Backend Dev", "role": "implementer"},
        ],
        "max_rounds": 2,
        "kanban_board_id": "board-raft-01",
    }
    res = debate_client.post(f"/chats/{chat_id}/debate-workrooms", json=create_payload)
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["room_id"] == "room-ws-test"
    assert data["phase"] == "decomposition"
    assert len(data["participants"]) == 3

    # 2. List rooms
    list_res = debate_client.get(f"/chats/{chat_id}/debate-workrooms")
    assert list_res.status_code == 200
    list_data = list_res.json()["data"]
    assert list_data["total"] == 1

    # 3. Leader Decomposes Task
    decomp_payload = {
        "subtasks": [
            {
                "task_id": "st-split-brain",
                "title": "Split-brain partition analysis",
                "description": "Assess behavior during 2-node netsplit",
                "assigned_agent_id": "agent-critic",
                "assigned_role": "critic",
                "status": "todo",
            },
            {
                "task_id": "st-log-compaction",
                "title": "Snapshot & log compaction",
                "description": "Implement RocksDB checkpointing",
                "assigned_agent_id": "agent-coder",
                "assigned_role": "implementer",
                "status": "todo",
            },
        ]
    }
    decomp_res = debate_client.post(
        f"/chats/{chat_id}/debate-workrooms/room-ws-test/decompose",
        json=decomp_payload,
    )
    assert decomp_res.status_code == 200
    decomp_data = decomp_res.json()["data"]
    assert decomp_data["phase"] == "round_argument"
    assert len(decomp_data["subtasks"]) == 2


def test_debate_argument_and_anti_wheel_war_and_convergence(debate_client: TestClient) -> None:
    chat_id = "chat-debate-002"
    room_id = "room-flow-test"

    # Setup room with max_rounds=1
    create_payload = {
        "room_id": room_id,
        "topic": "Evaluate GraphQL vs TRPC for internal admin portal",
        "leader_agent_id": "agent-lead",
        "participants": [
            {"agent_id": "agent-lead", "name": "Team Lead", "role": "leader"},
            {"agent_id": "agent-critic", "name": "Critic", "role": "critic"},
        ],
        "max_rounds": 1,
    }
    debate_client.post(f"/chats/{chat_id}/debate-workrooms", json=create_payload)

    # Decompose
    debate_client.post(
        f"/chats/{chat_id}/debate-workrooms/{room_id}/decompose",
        json={
            "subtasks": [
                {
                    "task_id": "st-schema",
                    "title": "Schema synchronization cost",
                    "description": "Evaluate codegen complexity",
                    "assigned_agent_id": "agent-critic",
                    "assigned_role": "critic",
                    "status": "todo",
                }
            ]
        },
    )

    # Post Turn 1: Round 1
    arg1_payload = {
        "speaker_id": "agent-critic",
        "thesis": "TRPC provides end-to-end type safety without GraphQL schema duplication",
        "counter_points": ["GraphQL requires extra AST parsing overhead"],
        "evidence": ["Benchmark demonstrates 2.4x lower latency on V8"],
        "confidence": 0.95,
    }
    arg1_res = debate_client.post(
        f"/chats/{chat_id}/debate-workrooms/{room_id}/argument",
        json=arg1_payload,
    )
    assert arg1_res.status_code == 200
    assert arg1_res.json()["data"]["speaker_name"] == "Critic"

    # Post Turn 2: triggers anti-wheel-war guard since round_index >= max_rounds (1)
    arg2_payload = {
        "speaker_id": "agent-lead",
        "thesis": "Agreed on TRPC benefits, will adopt for Next.js internal apps",
    }
    arg2_res = debate_client.post(
        f"/chats/{chat_id}/debate-workrooms/{room_id}/argument",
        json=arg2_payload,
    )
    assert arg2_res.status_code == 200
    assert arg2_res.json()["data"]["phase"] == "convergence"

    # Converge & Synthesize decision
    conv_payload = {
        "consensus_decision": "Standardize on TRPC for internal micro-frontends.",
        "settled_subtask_ids": ["st-schema"],
    }
    conv_res = debate_client.post(
        f"/chats/{chat_id}/debate-workrooms/{room_id}/converge",
        json=conv_payload,
    )
    assert conv_res.status_code == 200
    conv_data = conv_res.json()["data"]
    assert conv_data["phase"] == "settled"
    assert conv_data["subtasks"][0]["status"] == "done"

    # Kanban Card Sync
    sync_payload = {
        "kanban_task_id": "kanban-card-88",
        "kanban_status": "COMPLETED",
    }
    sync_res = debate_client.post(
        f"/chats/{chat_id}/debate-workrooms/{room_id}/subtasks/st-schema/kanban-sync",
        json=sync_payload,
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["data"]["kanban_task_id"] == "kanban-card-88"

    # Delete Room
    del_res = debate_client.delete(f"/chats/{chat_id}/debate-workrooms/{room_id}")
    assert del_res.status_code == 200
    assert del_res.json()["data"]["status"] == "deleted"
