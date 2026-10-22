"""The health endpoint reports the degraded-storage flags the web UI turns into user notices."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config.system_status import system_status
from tests.support.minimal_app import build_minimal_app

_client = TestClient(build_minimal_app(preset="health"))


@pytest.fixture(autouse=True)
def _reset_flags() -> Iterator[None]:
    system_status.vector_degraded = False
    system_status.database_degraded = False
    yield
    system_status.vector_degraded = False
    system_status.database_degraded = False


def test_health_reports_no_degradation_by_default() -> None:
    status = _client.get("/api/v1/health").json()["system_status"]

    assert status["vector_degraded"] is False
    assert status["database_degraded"] is False


def test_health_reports_vector_store_degradation() -> None:
    system_status.vector_degraded = True

    status = _client.get("/api/v1/health").json()["system_status"]

    assert status["vector_degraded"] is True
    assert status["database_degraded"] is False
