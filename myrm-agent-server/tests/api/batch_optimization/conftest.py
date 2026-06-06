"""Pytest fixtures for batch optimization API tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.batch_optimization.support import batch_router_module


@pytest.fixture
def batch_app() -> FastAPI:
    app = FastAPI()
    app.include_router(batch_router_module.router, prefix="/api/v1")
    return app


@pytest.fixture
def batch_client(batch_app: FastAPI) -> TestClient:
    with TestClient(batch_app) as test_client:
        yield test_client
