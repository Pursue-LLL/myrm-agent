"""Integration tests for /memory/follow-ups API with real SQLite store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.proactive.types import (
    CommitmentDueWindow,
    CommitmentKind,
    CommitmentRecord,
    CommitmentSensitivity,
    CommitmentStatus,
)

from app.api.memory.follow_ups.router import router as follow_ups_router
from tests.support.minimal_app import API_PREFIX

BASE = f"{API_PREFIX}/memory/follow-ups"


def _build_follow_ups_app() -> FastAPI:
    app = FastAPI(title="Follow-ups Integration Test App")
    api = APIRouter()
    api.include_router(follow_ups_router, prefix="/memory")
    app.include_router(api, prefix=API_PREFIX)
    return app


app = _build_follow_ups_app()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_record(*, record_id: str, agent_id: str = "api-int-agent") -> CommitmentRecord:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    return CommitmentRecord(
        id=record_id,
        agent_id=agent_id,
        user_id="default",
        channel="web",
        kind=CommitmentKind.EVENT_CHECK_IN,
        sensitivity=CommitmentSensitivity.ROUTINE,
        status=CommitmentStatus.PENDING,
        reason="integration interview",
        suggested_text="How is prep going?",
        dedupe_key=f"dedupe-{record_id}",
        confidence=0.88,
        due_window=CommitmentDueWindow(
            earliest_ms=now_ms,
            latest_ms=now_ms + 3600_000,
            timezone="UTC",
        ),
    )


@pytest.mark.asyncio
async def test_follow_ups_list_dismiss_snooze_flow(client: TestClient) -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    store = SqlAlchemyCommitmentStore()
    record = await store.upsert(_seed_record(record_id="cm_api_int_1"))

    list_resp = client.get(BASE)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] >= 1
    ids = {item["id"] for item in payload["items"]}
    assert record.id in ids

    filtered = client.get(BASE, params={"agent_id": record.agent_id, "status": "pending"})
    assert filtered.status_code == 200
    assert any(item["id"] == record.id for item in filtered.json()["items"])

    snooze_until = int(datetime.now(UTC).timestamp() * 1000) + 4 * 3600_000
    snooze_resp = client.post(
        f"{BASE}/{record.id}/snooze",
        json={"until_ms": snooze_until},
    )
    assert snooze_resp.status_code == 200
    assert snooze_resp.json()["success"] is True

    after_snooze = client.get(BASE, params={"status": "snoozed"})
    assert any(item["id"] == record.id for item in after_snooze.json()["items"])

    dismiss_resp = client.post(f"{BASE}/{record.id}/dismiss")
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["success"] is True

    dismissed = client.get(BASE, params={"status": "dismissed"})
    assert any(item["id"] == record.id for item in dismissed.json()["items"])


def test_follow_ups_snooze_rejects_past_timestamp(client: TestClient) -> None:
    past_ms = int(datetime.now(UTC).timestamp() * 1000) - 1000
    resp = client.post(
        f"{BASE}/cm_missing/snooze",
        json={"until_ms": past_ms},
    )
    assert resp.status_code == 400


def test_follow_ups_dismiss_unknown_returns_404(client: TestClient) -> None:
    resp = client.post(f"{BASE}/cm_does_not_exist/dismiss")
    assert resp.status_code == 404


def test_follow_ups_invalid_status_returns_400(client: TestClient) -> None:
    resp = client.get(BASE, params={"status": "not_a_status"})
    assert resp.status_code == 400
    assert "Invalid status" in resp.json()["detail"]
