from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import pressure as pressure_module


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(pressure_module.router, prefix="/health")
    return TestClient(app)


def test_pressure_unknown_when_monitor_missing(monkeypatch) -> None:
    monkeypatch.setattr(pressure_module, "_memory_state", lambda: {"level": "unknown", "percent": None})
    client = _app()
    response = client.get("/health/pressure")
    assert response.status_code == 200
    payload = response.json()
    assert payload["memory"]["level"] == "unknown"
    assert "disk" in payload
    assert payload["thresholds"]["disk_warn_percent"] == 85.0
    assert payload["thresholds"]["disk_critical_percent"] == 95.0


def test_pressure_reports_critical_memory(monkeypatch) -> None:
    monkeypatch.setattr(
        pressure_module,
        "_memory_state",
        lambda: {"level": "critical", "percent": 96.2},
    )
    client = _app()
    response = client.get("/health/pressure")
    assert response.status_code == 200
    assert response.json()["memory"]["level"] == "critical"


def test_disk_state_thresholds(tmp_path) -> None:
    from app.api.health.pressure import _disk_state

    state = _disk_state(str(tmp_path))
    assert state["state"] in {"ok", "elevated", "critical"}
    assert isinstance(state["percent"], float)
    assert isinstance(state["free_bytes"], int)


def test_disk_state_unknown_for_missing_path() -> None:
    import pytest as _pytest

    from app.api.health.pressure import _disk_state

    with _pytest.MonkeyPatch.context() as mp:
        import shutil as _shutil

        def _boom(_path):  # noqa: ANN001, ANN202
            raise OSError("no disk")

        mp.setattr(_shutil, "disk_usage", _boom)
        state = _disk_state("/tmp")
    assert state["state"] == "unknown"
    assert state["percent"] is None
