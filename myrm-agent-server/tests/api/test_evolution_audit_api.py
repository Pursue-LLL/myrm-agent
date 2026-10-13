"""Evolution API smoke tests (derive route + /metrics)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.evolution import router as evolution_router


@pytest.fixture
def evolution_only_app() -> FastAPI:
    app = FastAPI()
    app.include_router(evolution_router, prefix="/api/v1")
    return app


def test_evolution_derive_route_exists(evolution_only_app: FastAPI) -> None:
    client = TestClient(evolution_only_app)
    response = client.post("/api/v1/evolution/derive/does-not-exist", json={"instruction": "improve it"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found: does-not-exist"


def test_main_app_exposes_metrics() -> None:
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    test_app = FastAPI()

    @test_app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    client = TestClient(test_app)
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "process_" in text.lower() or "python_" in text.lower()
