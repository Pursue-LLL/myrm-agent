from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def test_get_ingress_url(client):
    with patch("app.api.system.router.get_public_ingress_base_url", new_callable=AsyncMock) as mock_get_url:
        mock_get_url.return_value = "https://example.com"

        response = client.get("/api/v1/system/ingress-url")
        assert response.status_code == 200
        assert response.json() == {"ingress_url": "https://example.com"}
        mock_get_url.assert_awaited_once()
