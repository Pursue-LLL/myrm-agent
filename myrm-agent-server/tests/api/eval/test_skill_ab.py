"""Unit tests for Skill A/B evaluation service and router."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.eval.skill_ab import (
    abort_skill_ab,
    get_latest_skill_ab_report,
    get_skill_ab_report_history,
    get_skill_ab_status,
)
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def client() -> TestClient:
    minimal_app = build_minimal_app(preset="eval")
    return TestClient(minimal_app)


def test_skill_ab_status_and_abort() -> None:
    status = get_skill_ab_status()
    assert isinstance(status, dict)
    assert "is_running" in status

    aborted = abort_skill_ab()
    assert isinstance(aborted, bool)


def test_skill_ab_reports_dir_empty(tmp_path: Path) -> None:
    assert get_latest_skill_ab_report(tmp_path) is None
    assert get_skill_ab_report_history(tmp_path) == []


def test_skill_ab_reports_dir_with_data(tmp_path: Path) -> None:
    report_data = {
        "dataset_id": "test-ds",
        "candidate_skill_id": "cand-v2",
        "baseline_skill_id": "base-v1",
        "verdict": "IMPROVED",
        "success_rate_delta": 0.25,
        "created_at": "2026-08-25T12:00:00Z",
    }
    report_file = tmp_path / "skill_ab_test-ds_1700000000.json"
    latest_file = tmp_path / "latest.json"

    with report_file.open("w", encoding="utf-8") as f:
        json.dump(report_data, f)
    with latest_file.open("w", encoding="utf-8") as f:
        json.dump(report_data, f)

    latest = get_latest_skill_ab_report(tmp_path)
    assert latest is not None
    assert latest["candidate_skill_id"] == "cand-v2"
    assert latest["verdict"] == "IMPROVED"

    history = get_skill_ab_report_history(tmp_path)
    assert len(history) == 1
    assert history[0]["candidate_skill_id"] == "cand-v2"


def test_skill_ab_router_status(client: TestClient) -> None:
    resp = client.get("/api/v1/eval/skill-ab/status")
    assert resp.status_code == 200
    assert "is_running" in resp.json()


def test_skill_ab_router_abort(client: TestClient) -> None:
    resp = client.post("/api/v1/eval/skill-ab/abort")
    assert resp.status_code == 200
    assert "aborted" in resp.json()


def test_skill_ab_router_reports(client: TestClient) -> None:
    resp = client.get("/api/v1/eval/skill-ab/reports")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
