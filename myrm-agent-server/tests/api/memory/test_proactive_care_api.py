"""[POS]: tests/api/memory/test_proactive_care_api.py
[INPUT]: None.
[OUTPUT]: Isolated integration tests for proactive care and schedule rebalancing endpoints.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.proactive_care import router
from app.services.memory.proactive_care import ProactiveCareProvider


@pytest.fixture(autouse=True)
def setup_isolated_provider(tmp_path: Path):
    db_file = tmp_path / "test_proactive_care.db"
    ProactiveCareProvider.set_custom_db_path(db_file)
    yield
    ProactiveCareProvider.reset()


@pytest.mark.asyncio
async def test_proactive_care_workflow_end_to_end() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sync Health Metrics (sleep deprivation and high resting heart rate)
        sync_resp = await client.post(
            "/api/memory/proactive-care/sync-health",
            json={
                "user_id": "test_user_80",
                "sleep_duration_hours": 4.1,
                "deep_sleep_ratio": 0.08,
                "daily_steps": 2100,
                "resting_heart_rate": 86,
                "recorded_at_iso": "2026-10-08T01:00:00Z",
            },
        )
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["user_id"] == "test_user_80"
        assert sync_data["sleep_duration_hours"] == 4.1

        # 2. Record subtle conversational cue
        cue_resp = await client.post(
            "/api/memory/proactive-care/record-cue",
            json={
                "user_id": "test_user_80",
                "cue_text": "昨晚通宵改 bug，头痛欲裂",
            },
        )
        assert cue_resp.status_code == 200
        assert cue_resp.json()["status"] is True

        # 3. Evaluate vitality report
        report_resp = await client.get(
            "/api/memory/proactive-care/vitality-report?user_id=test_user_80"
        )
        assert report_resp.status_code == 200
        report_data = report_resp.json()
        assert report_data["fatigue_level"] == "severe_overdraw"
        assert report_data["vitality_score"] < 0.45
        assert len(report_data["causal_factors"]) >= 1

        # 4. Proactive schedule rebalancing & care notification dispatch
        rebalance_resp = await client.post(
            "/api/memory/proactive-care/rebalance-schedule",
            json={
                "user_id": "test_user_80",
                "force_notify": True,
                "tasks": [
                    {
                        "task_id": "workout-101",
                        "title": "高强度下肢力量深蹲",
                        "scheduled_date": "2026-10-08",
                        "intensity_level": 4,
                        "category": "workout",
                        "is_flexible": True,
                        "original_duration_minutes": 60,
                        "adjusted_duration_minutes": 60,
                        "status": "active",
                    },
                    {
                        "task_id": "meeting-202",
                        "title": "客户交付评审会",
                        "scheduled_date": "2026-10-08",
                        "intensity_level": 3,
                        "category": "meeting",
                        "is_flexible": False,
                        "original_duration_minutes": 45,
                        "adjusted_duration_minutes": 45,
                        "status": "active",
                    },
                ],
            },
        )
        assert rebalance_resp.status_code == 200
        rebalance_data = rebalance_resp.json()
        assert rebalance_data["fatigue_level"] == "severe_overdraw"
        assert rebalance_data["load_reduction_ratio"] == 0.50

        # Verify task load scaling: workout scaled to 30 mins, meeting unchanged
        tasks_res = rebalance_data["tasks_modified"]
        workout = next(t for t in tasks_res if t["task_id"] == "workout-101")
        meeting = next(t for t in tasks_res if t["task_id"] == "meeting-202")
        assert workout["adjusted_duration_minutes"] == 30
        assert meeting["adjusted_duration_minutes"] == 45

        # Verify empathetic care notification
        care_notif = rebalance_data["care_notification"]
        assert care_notif is not None
        assert "喘口气" in care_notif["title"]
        assert "懂你" in care_notif["content_message"]
        notif_id = care_notif["notification_id"]

        # 5. List care notifications
        list_resp = await client.get(
            "/api/memory/proactive-care/care-notifications?user_id=test_user_80"
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total_count"] >= 1
        assert list_data["notifications"][0]["is_read"] is False

        # 6. Mark notification as read
        read_resp = await client.post(
            f"/api/memory/proactive-care/care-notifications/{notif_id}/read"
        )
        assert read_resp.status_code == 200
        assert read_resp.json()["status"] is True

        # Check unread count is now 0
        unread_resp = await client.get(
            "/api/memory/proactive-care/care-notifications?user_id=test_user_80&unread_only=true"
        )
        assert unread_resp.status_code == 200
        assert unread_resp.json()["total_count"] == 0
