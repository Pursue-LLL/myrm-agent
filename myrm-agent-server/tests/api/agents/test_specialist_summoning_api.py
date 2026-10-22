"""Unit tests for Conversational Multi-Specialist Summoning & Context Aggregation API (Item 54).

[INPUT]
- app.api.agents.specialist_summoning_router.router
- app.services.agent.specialist_summoning_service.SpecialistSummoningService

[OUTPUT]
- Pytest test cases validating specialist catalog discovery, @-mention and intent sensing,
  isolated sandbox execution, and structured aggregation card history.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_specialist_summoning_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.specialist_summoning_router import (
    get_service,
)
from app.api.agents.specialist_summoning_router import (
    router as specialist_summoning_router,
)
from app.services.agent.specialist_summoning_service import (
    SpecialistSummoningService,
)


@pytest.fixture
def service() -> SpecialistSummoningService:
    SpecialistSummoningService.reset_instance()
    return SpecialistSummoningService.get_instance()


@pytest.fixture
def client(
    service: SpecialistSummoningService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(specialist_summoning_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_specialist_catalog_api(client: TestClient) -> None:
    """Verifies retrieval of full catalog containing all vertical specialists."""
    res = client.get("/agents/specialists/catalog")
    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 5

    ids = [p["specialist_id"] for p in data]
    assert "specialist_humanize" in ids
    assert "specialist_visual" in ids
    assert "specialist_code_audit" in ids


def test_get_specialist_detail_api(client: TestClient) -> None:
    """Verifies getting details of an existing specialist and 404 for unknown specialist."""
    res = client.get("/agents/specialists/specialist_humanize")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["specialist_id"] == "specialist_humanize"
    assert data["mention_tag"] == "@去AI味专家"

    # Query unknown
    not_found = client.get("/agents/specialists/specialist_unknown_999")
    assert not_found.status_code == 404


def test_detect_specialist_intent_explicit_mention_api(client: TestClient) -> None:
    """Verifies intent detection parses explicit @-mention tag."""
    payload = {"message": "@去AI味专家 帮我把这段文案改得更通俗自然一些"}
    res = client.post("/agents/specialists/detect-intent", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["matched"] is True
    assert data["trigger_source"] == "explicit_mention"
    assert data["cleaned_instruction"] == "帮我把这段文案改得更通俗自然一些"
    assert data["specialist"]["specialist_id"] == "specialist_humanize"


def test_detect_specialist_intent_implicit_keywords_api(client: TestClient) -> None:
    """Verifies implicit intent detection matching keywords."""
    payload = {"message": "核心逻辑写完了，现在请协助做一次全量代码审计与安全漏洞排查"}
    res = client.post("/agents/specialists/detect-intent", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["matched"] is True
    assert data["trigger_source"] == "intent_detection"
    assert data["specialist"]["specialist_id"] == "specialist_code_audit"


def test_summon_specialist_isolated_execution_api(client: TestClient) -> None:
    """Verifies isolated execution returns structured aggregation card and updates session history."""
    chat_id = "chat-summon-test-01"
    payload = {
        "specialist_id": "specialist_visual",
        "instruction": "为发布会演讲准备 3 套极简风格的视觉配色与插图方案",
        "trigger_source": "explicit_mention",
        "parent_context_slice": "发布会主打简洁科技感",
    }

    res = client.post(f"/chats/{chat_id}/specialists/summon", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "completed"
    assert data["specialist_id"] == "specialist_visual"
    assert data["aggregation_card"] is not None

    card = data["aggregation_card"]
    assert card["card_type"] == "visual_spec"
    assert "视觉与配图设计专家" in card["specialist_name"]
    assert len(card["artifacts"]) > 0

    # Query session executions
    history_res = client.get(f"/chats/{chat_id}/specialists/executions")
    assert history_res.status_code == 200
    history_data = history_res.json()["data"]
    assert len(history_data) == 1
    assert history_data[0]["summon_id"] == data["summon_id"]


def test_clear_session_executions_api(client: TestClient) -> None:
    """Verifies clearing session specialist execution history."""
    chat_id = "chat-clear-02"
    # Execute one summon
    payload = {
        "specialist_id": "specialist_market_research",
        "instruction": "调研竞品定价模式",
        "trigger_source": "intent_detection",
    }
    client.post(f"/chats/{chat_id}/specialists/summon", json=payload)

    # Verify present
    res1 = client.get(f"/chats/{chat_id}/specialists/executions")
    assert len(res1.json()["data"]) == 1

    # Clear
    del_res = client.delete(f"/chats/{chat_id}/specialists/executions")
    assert del_res.status_code == 200

    # Verify empty
    res2 = client.get(f"/chats/{chat_id}/specialists/executions")
    assert len(res2.json()["data"]) == 0
