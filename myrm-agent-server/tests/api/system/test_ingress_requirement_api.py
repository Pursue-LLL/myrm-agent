from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router
from app.core.infra.ingress_requirement import IngressRequirementSnapshot, invalidate_ingress_requirement_cache


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def test_get_ingress_requirement(client):
    invalidate_ingress_requirement_cache()
    snapshot = IngressRequirementSnapshot(
        required=True,
        has_public_ingress=False,
        reasons=("channel:line",),
        channels={"line": "inbound", "feishu": "outbound"},
    )
    with patch("app.api.system.router.resolve_ingress_requirement", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = snapshot
        response = client.get("/api/v1/system/ingress-requirement")
        assert response.status_code == 200
        assert response.json() == {
            "required": True,
            "has_public_ingress": False,
            "reasons": ["channel:line"],
            "channels": {"line": "inbound", "feishu": "outbound"},
        }
        mock_resolve.assert_awaited_once()
