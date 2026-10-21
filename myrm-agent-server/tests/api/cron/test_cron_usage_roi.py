"""Unit and contract tests for Cron usage stats ROI and saved hours visualizer backend.

[INPUT]
- app.api.cron.routes.stats::router (POS: cron stats router)
- app.api.cron.schemas::UsageStatsResponse (POS: Pydantic response schema)

[OUTPUT]
- Test cases for /stats/usage endpoint with estimated_hours_saved and roi_multiple metrics.

[POS]
Tests API contract and logic for Item 3: AutomatedTasksSavedHoursAndROIVisualizer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.cron.routes.stats import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI(title="Cron Stats ROI Test App")
    app.include_router(router, prefix="/api/v1/cron")
    return TestClient(app, raise_server_exceptions=True)


def test_usage_stats_empty_runs_roi_zero(client: TestClient) -> None:
    fake_result = {
        "summary": {
            "total_runs": 0,
            "success_runs": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "avg_tokens_per_run": 0,
            "estimated_hours_saved": 0.0,
            "roi_multiple": 0.0,
            "estimated_value_saved_cents": 0.0,
            "estimated_cost_cents": 0.0,
        },
        "by_day": [],
        "by_job": [],
        "by_model": [],
    }

    with patch("app.core.cron.adapters.sqlalchemy_aggregation.aggregate_usage", new_callable=AsyncMock) as mock_agg:
        mock_agg.return_value = fake_result
        res = client.get("/api/v1/cron/stats/usage?days=7")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["summary"]["total_runs"] == 0
        assert data["summary"]["estimated_hours_saved"] == 0.0
        assert data["summary"]["roi_multiple"] == 0.0
        assert data["summary"]["estimated_value_saved_cents"] == 0.0
        assert data["summary"]["estimated_cost_cents"] == 0.0


def test_usage_stats_with_runs_roi_and_hours_saved(client: TestClient) -> None:
    fake_result = {
        "summary": {
            "total_runs": 12,
            "success_runs": 10,
            "total_input_tokens": 60000,
            "total_output_tokens": 40000,
            "total_tokens": 100000,
            "avg_tokens_per_run": 8333,
            "estimated_hours_saved": 1.7,
            "roi_multiple": 250.0,
            "estimated_value_saved_cents": 5000.0,
            "estimated_cost_cents": 20.0,
        },
        "by_day": [
            {
                "date": "2026-10-10",
                "input_tokens": 60000,
                "output_tokens": 40000,
                "total_tokens": 100000,
                "runs": 12,
            }
        ],
        "by_job": [
            {
                "job_id": "job-daily-report",
                "job_name": "Daily Report",
                "total_tokens": 60000,
                "runs": 6,
                "hours_saved": 1.0,
            },
            {
                "job_id": "job-news-digest",
                "job_name": "News Digest",
                "total_tokens": 40000,
                "runs": 6,
                "hours_saved": 1.0,
            },
        ],
        "by_model": [
            {
                "model": "gpt-4o-mini",
                "total_tokens": 100000,
                "runs": 12,
            }
        ],
    }

    with patch("app.core.cron.adapters.sqlalchemy_aggregation.aggregate_usage", new_callable=AsyncMock) as mock_agg:
        mock_agg.return_value = fake_result
        res = client.get("/api/v1/cron/stats/usage?days=30")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["summary"]["total_runs"] == 12
        assert data["summary"]["success_runs"] == 10
        assert data["summary"]["estimated_hours_saved"] == 1.7
        assert data["summary"]["roi_multiple"] == 250.0
        assert data["summary"]["estimated_value_saved_cents"] == 5000.0
        assert data["summary"]["estimated_cost_cents"] == 20.0

        # Check by_job hours_saved
        assert len(data["by_job"]) == 2
        assert data["by_job"][0]["job_name"] == "Daily Report"
        assert data["by_job"][0]["hours_saved"] == 1.0
        assert data["by_job"][1]["job_name"] == "News Digest"
        assert data["by_job"][1]["hours_saved"] == 1.0
