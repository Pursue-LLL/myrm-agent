"""Integration tests for Four-Layer Memory promotion audit API endpoints.

[INPUT]
- fastapi::FastAPI
- starlette.testclient::TestClient
- app.api.memory.four_layer_promotion_router::router
- myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion (engine and audit tracker used to seed promoted methods)

[OUTPUT]
- Pytest cases verifying active-method listing, rules compliance, and batch rollback

[POS]
Server-side integration testing for anti-poisoning lineage audit over promoted capability methods.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion import (
    AntiPoisoningAuditTracker,
    CandidateStatement,
    ExposureSource,
    TwoStepMapReduceConsolidationEngine,
)
from starlette.testclient import TestClient

from app.api.memory.four_layer_promotion_router import (
    router as four_layer_promotion_router,
)
from app.services.memory.four_layer_promotion_service import (
    FourLayerPromotionService,
    get_four_layer_promotion_service,
)


@pytest.fixture
def seeded_batch() -> tuple[FourLayerPromotionService, str, str]:
    """Promote one tool-failure method into a fresh tracker; return (service, batch_id, method_id)."""
    engine = TwoStepMapReduceConsolidationEngine()
    tracker = AntiPoisoningAuditTracker()
    methods, _decisions = engine.reduce_cross_session(
        [
            CandidateStatement(
                statement="兵马俑和回民街不能塞在同一天",
                supported_event_ids=("evt-202",),
                session_id="sess-xian-trip",
                exposure_source=ExposureSource.INTERNAL_CHAT,
                has_tool_failure=True,
                is_explicit_user_instruction=False,
            )
        ]
    )
    batch_id = tracker.record_batch(methods)
    return FourLayerPromotionService(engine=engine, tracker=tracker), batch_id, methods[0].method_id


@pytest.fixture
def client(seeded_batch: tuple[FourLayerPromotionService, str, str]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(four_layer_promotion_router, prefix="/api/memory")
    app.dependency_overrides[get_four_layer_promotion_service] = lambda: seeded_batch[0]
    with TestClient(app) as test_client:
        yield test_client


def test_list_active_methods(client: TestClient, seeded_batch: tuple[FourLayerPromotionService, str, str]) -> None:
    _service, _batch_id, method_id = seeded_batch
    resp = client.get("/api/memory/four-layer-promotion/active-methods")
    assert resp.status_code == 200
    data = resp.json()
    assert [m["method_id"] for m in data] == [method_id]
    assert data[0]["promotion_channel"] == "tool_failure_evidence"


def test_verify_compliance_and_rollback(
    client: TestClient, seeded_batch: tuple[FourLayerPromotionService, str, str]
) -> None:
    _service, batch_id, method_id = seeded_batch

    verify_resp = client.post(
        "/api/memory/four-layer-promotion/verify-compliance",
        json={"response_text": "建议行程安排合理，没有任何错误"},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["all_compliant"] is True

    rollback_resp = client.post(
        "/api/memory/four-layer-promotion/rollback",
        json={"batch_id": batch_id},
    )
    assert rollback_resp.status_code == 200
    rollback_data = rollback_resp.json()
    assert rollback_data["success"] is True
    assert method_id in rollback_data["reverted_method_ids"]

    assert client.get("/api/memory/four-layer-promotion/active-methods").json() == []
