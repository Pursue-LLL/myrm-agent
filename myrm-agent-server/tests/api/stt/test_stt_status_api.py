"""Unit tests for GET /stt/status API endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.stt.router import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/stt")
    return TestClient(app)


class TestSTTStatusEndpoint:
    def test_status_local_not_available(self, client: TestClient) -> None:
        with patch(
            "app.channels.voice.stt.get_local_status",
            return_value={"available": False, "model_loaded": False, "config": None},
        ):
            resp = client.get("/stt/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["model_loaded"] is False
        assert body["config"] is None

    def test_status_local_available_not_loaded(self, client: TestClient) -> None:
        with patch(
            "app.channels.voice.stt.get_local_status",
            return_value={"available": True, "model_loaded": False, "config": None},
        ):
            resp = client.get("/stt/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["model_loaded"] is False

    def test_status_local_loaded(self, client: TestClient) -> None:
        with patch(
            "app.channels.voice.stt.get_local_status",
            return_value={
                "available": True,
                "model_loaded": True,
                "config": {"model_size": "base", "device": "cpu", "compute_type": "int8"},
            },
        ):
            resp = client.get("/stt/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["model_loaded"] is True
        assert body["config"]["model_size"] == "base"
        assert body["config"]["device"] == "cpu"
        assert body["config"]["compute_type"] == "int8"
