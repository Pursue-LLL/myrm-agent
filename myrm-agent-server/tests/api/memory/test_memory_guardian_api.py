"""API tests for memory guardian trigger/policy/digest endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import guardian as guardian_operation
from app.lifecycle import memory_guardian
from app.services.memory.guardian_policy import MemoryGuardianPolicy


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(guardian_operation.router, prefix="/api/v1/memory")

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _fake_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_trigger_maintenance_defaults_to_safe_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_mock = AsyncMock(return_value={"triggered": True, "mode": "safe", "applied": False})
    monkeypatch.setattr(memory_guardian, "run_memory_guardian_once", run_mock)

    response = client.post("/api/v1/memory/guardian/trigger")

    assert response.status_code == 200
    assert response.json()["mode"] == "safe"
    run_mock.assert_awaited_once_with(mode="safe")


def test_trigger_maintenance_supports_force_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    run_mock = AsyncMock(return_value={"triggered": True, "mode": "force", "applied": True})
    monkeypatch.setattr(memory_guardian, "run_memory_guardian_once", run_mock)

    response = client.post("/api/v1/memory/guardian/trigger", json={"mode": "force"})

    assert response.status_code == 200
    assert response.json()["mode"] == "force"
    run_mock.assert_awaited_once_with(mode="force")


def test_get_guardian_policy(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = MemoryGuardianPolicy(
        frequency_tier="aggressive",
        quiet_window_enabled=True,
        quiet_window_start_hour=23,
        quiet_window_end_hour=7,
        timezone_offset_minutes=480,
    )
    load_mock = AsyncMock(return_value=policy)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)

    response = client.get("/api/v1/memory/guardian/policy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["frequency_tier"] == "aggressive"
    assert payload["quiet_window_enabled"] is True
    assert payload["quiet_window_start_hour"] == 23
    assert payload["quiet_window_end_hour"] == 7


def test_update_guardian_policy(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    save_mock = AsyncMock(side_effect=lambda policy: policy)
    monkeypatch.setattr(guardian_operation, "save_memory_guardian_policy", save_mock)

    response = client.put(
        "/api/v1/memory/guardian/policy",
        json={
            "frequency_tier": "conservative",
            "quiet_window_enabled": True,
            "quiet_window_start_hour": 1,
            "quiet_window_end_hour": 6,
            "timezone_offset_minutes": 540,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["frequency_tier"] == "conservative"
    assert payload["quiet_window_enabled"] is True
    assert payload["quiet_window_start_hour"] == 1
    assert payload["quiet_window_end_hour"] == 6
    assert payload["timezone_offset_minutes"] == 540
    assert save_mock.await_count == 1
    saved_policy = save_mock.await_args.args[0]
    assert isinstance(saved_policy, MemoryGuardianPolicy)


def test_get_guardian_morning_digest(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = MemoryGuardianPolicy(timezone_initialized=True)
    load_mock = AsyncMock(return_value=policy)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)
    digest_mock = AsyncMock(
        return_value={
            "available": True,
            "summary": "Guardian maintenance: merged 2, corrected 1",
            "counts": {
                "merged": 2,
                "corrected": 1,
                "forgotten": 0,
                "archived": 0,
                "stale_removed": 0,
                "stale_extended": 0,
            },
        }
    )
    monkeypatch.setattr(
        guardian_operation.MemoryOperationLedgerService,
        "latest_guardian_morning_digest",
        digest_mock,
    )

    response = client.get("/api/v1/memory/guardian/morning-digest")

    assert response.status_code == 200
    assert response.json()["available"] is True
    digest_mock.assert_awaited_once()
    assert digest_mock.await_args.kwargs["policy"] is policy


def test_get_guardian_overview_returns_health_and_digest(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = AsyncMock()
    fake_manager.compute_health_score.return_value = SimpleNamespace(
        to_dict=lambda: {"total": 88, "dimensions": {}, "suggestions": [], "has_graph": False}
    )

    async def _override_memory_manager() -> AsyncMock:
        return fake_manager

    client.app.dependency_overrides[guardian_operation.get_crud_memory_manager] = _override_memory_manager
    policy = MemoryGuardianPolicy(timezone_offset_minutes=480, timezone_initialized=True)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", AsyncMock(return_value=policy))
    monkeypatch.setattr(
        memory_guardian,
        "get_memory_guardian_status",
        lambda *, policy: {"running": False, "timezone_offset_minutes": policy.timezone_offset_minutes},
    )
    digest_mock = AsyncMock(return_value={"available": True, "summary": "night digest"})
    monkeypatch.setattr(
        guardian_operation.MemoryOperationLedgerService,
        "latest_guardian_morning_digest",
        digest_mock,
    )
    alert_mock = AsyncMock(
        return_value={
            "active": False,
            "escalated": False,
            "window_hours": 24,
            "total": 0,
            "reasons": {},
            "dominant_reason": None,
            "dominant_reason_count": 0,
            "dominant_reason_ratio": 0.0,
            "thresholds": {
                "min_total_events": 2,
                "escalation_min_reason_count": 2,
                "escalation_min_reason_ratio": 0.6,
            },
            "last_occurred_at": None,
        }
    )
    monkeypatch.setattr(
        guardian_operation.MemoryOperationLedgerService,
        "guardian_guard_alert_snapshot",
        alert_mock,
    )

    response = client.get("/api/v1/memory/guardian/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["total"] == 88
    assert payload["policy"]["timezone_offset_minutes"] == 480
    assert payload["digest"] == {"available": True, "summary": "night digest"}
    digest_mock.assert_awaited_once()


def test_get_memory_health_bootstraps_timezone_from_request_header(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = AsyncMock()
    fake_manager.compute_health_score.return_value = SimpleNamespace(
        to_dict=lambda: {"total": 83, "dimensions": {}, "suggestions": [], "has_graph": False}
    )

    async def _override_memory_manager() -> AsyncMock:
        return fake_manager

    client.app.dependency_overrides[guardian_operation.get_crud_memory_manager] = _override_memory_manager
    policy = MemoryGuardianPolicy(timezone_offset_minutes=480, timezone_initialized=True)
    bootstrap_mock = AsyncMock(return_value=policy)
    load_mock = AsyncMock(return_value=MemoryGuardianPolicy())
    monkeypatch.setattr(guardian_operation, "ensure_memory_guardian_timezone_initialized", bootstrap_mock)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)
    monkeypatch.setattr(
        memory_guardian,
        "get_memory_guardian_status",
        lambda *, policy: {"running": False, "timezone_offset_minutes": policy.timezone_offset_minutes},
    )

    response = client.get(
        "/api/v1/memory/guardian/health",
        headers={"x-client-timezone-offset-minutes": "480"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"]["timezone_offset_minutes"] == 480
    assert "alerts" in payload
    assert "guard_unavailable" in payload["alerts"]
    bootstrap_mock.assert_awaited_once_with(480, source="client_header")
    load_mock.assert_not_awaited()


def test_get_memory_health_bootstraps_timezone_from_alias_header(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = AsyncMock()
    fake_manager.compute_health_score.return_value = SimpleNamespace(
        to_dict=lambda: {"total": 79, "dimensions": {}, "suggestions": [], "has_graph": False}
    )

    async def _override_memory_manager() -> AsyncMock:
        return fake_manager

    client.app.dependency_overrides[guardian_operation.get_crud_memory_manager] = _override_memory_manager
    policy = MemoryGuardianPolicy(timezone_offset_minutes=540, timezone_initialized=True)
    bootstrap_mock = AsyncMock(return_value=policy)
    load_mock = AsyncMock(return_value=MemoryGuardianPolicy())
    monkeypatch.setattr(guardian_operation, "ensure_memory_guardian_timezone_initialized", bootstrap_mock)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)
    monkeypatch.setattr(
        memory_guardian,
        "get_memory_guardian_status",
        lambda *, policy: {"running": False, "timezone_offset_minutes": policy.timezone_offset_minutes},
    )

    response = client.get(
        "/api/v1/memory/guardian/health",
        headers={"x-timezone-offset-minutes": "540"},
    )

    assert response.status_code == 200
    assert response.json()["policy"]["timezone_offset_minutes"] == 540
    bootstrap_mock.assert_awaited_once_with(540, source="client_header")
    load_mock.assert_not_awaited()


def test_get_memory_health_bootstraps_timezone_from_server_fallback_when_uninitialized(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = AsyncMock()
    fake_manager.compute_health_score.return_value = SimpleNamespace(
        to_dict=lambda: {"total": 81, "dimensions": {}, "suggestions": [], "has_graph": False}
    )

    async def _override_memory_manager() -> AsyncMock:
        return fake_manager

    client.app.dependency_overrides[guardian_operation.get_crud_memory_manager] = _override_memory_manager
    load_mock = AsyncMock(return_value=MemoryGuardianPolicy(timezone_initialized=False, timezone_offset_minutes=0))
    bootstrap_policy = MemoryGuardianPolicy(timezone_initialized=True, timezone_offset_minutes=330)
    bootstrap_mock = AsyncMock(return_value=bootstrap_policy)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)
    monkeypatch.setattr(guardian_operation, "ensure_memory_guardian_timezone_initialized", bootstrap_mock)
    monkeypatch.setattr(guardian_operation, "_server_local_timezone_offset_minutes", lambda: 330)
    monkeypatch.setattr(
        memory_guardian,
        "get_memory_guardian_status",
        lambda *, policy: {"running": False, "timezone_offset_minutes": policy.timezone_offset_minutes},
    )

    response = client.get("/api/v1/memory/guardian/health")

    assert response.status_code == 200
    assert response.json()["policy"]["timezone_offset_minutes"] == 330
    load_mock.assert_awaited_once()
    bootstrap_mock.assert_awaited_once_with(330, source="server_fallback")


def test_get_memory_health_uses_initialized_policy_without_bootstrap(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = AsyncMock()
    fake_manager.compute_health_score.return_value = SimpleNamespace(
        to_dict=lambda: {"total": 77, "dimensions": {}, "suggestions": [], "has_graph": False}
    )

    async def _override_memory_manager() -> AsyncMock:
        return fake_manager

    client.app.dependency_overrides[guardian_operation.get_crud_memory_manager] = _override_memory_manager
    loaded_policy = MemoryGuardianPolicy(timezone_initialized=True, timezone_offset_minutes=120)
    load_mock = AsyncMock(return_value=loaded_policy)
    bootstrap_mock = AsyncMock(return_value=loaded_policy)
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)
    monkeypatch.setattr(guardian_operation, "ensure_memory_guardian_timezone_initialized", bootstrap_mock)
    monkeypatch.setattr(
        memory_guardian,
        "get_memory_guardian_status",
        lambda *, policy: {"running": False, "timezone_offset_minutes": policy.timezone_offset_minutes},
    )

    response = client.get("/api/v1/memory/guardian/health")

    assert response.status_code == 200
    assert response.json()["policy"]["timezone_offset_minutes"] == 120
    load_mock.assert_awaited_once()
    bootstrap_mock.assert_not_awaited()


def test_get_memory_health_falls_back_to_loaded_policy_when_bootstrap_raises(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = AsyncMock()
    fake_manager.compute_health_score.return_value = SimpleNamespace(
        to_dict=lambda: {"total": 75, "dimensions": {}, "suggestions": [], "has_graph": False}
    )

    async def _override_memory_manager() -> AsyncMock:
        return fake_manager

    client.app.dependency_overrides[guardian_operation.get_crud_memory_manager] = _override_memory_manager
    loaded_policy = MemoryGuardianPolicy(timezone_initialized=False, timezone_offset_minutes=0)
    load_mock = AsyncMock(return_value=loaded_policy)
    bootstrap_mock = AsyncMock(side_effect=RuntimeError("bootstrap failed"))
    monkeypatch.setattr(guardian_operation, "load_memory_guardian_policy", load_mock)
    monkeypatch.setattr(guardian_operation, "ensure_memory_guardian_timezone_initialized", bootstrap_mock)
    monkeypatch.setattr(guardian_operation, "_server_local_timezone_offset_minutes", lambda: 480)
    monkeypatch.setattr(
        memory_guardian,
        "get_memory_guardian_status",
        lambda *, policy: {"running": False, "timezone_offset_minutes": policy.timezone_offset_minutes},
    )

    response = client.get("/api/v1/memory/guardian/health")

    assert response.status_code == 200
    assert response.json()["policy"]["timezone_offset_minutes"] == 0
    load_mock.assert_awaited_once()
    bootstrap_mock.assert_awaited_once_with(480, source="server_fallback")
