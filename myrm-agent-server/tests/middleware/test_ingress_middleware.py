from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.ingress import PublicIngressMiddleware, should_skip_ingress_rewrite


@pytest.fixture
def app():
    _app = FastAPI()
    _app.add_middleware(PublicIngressMiddleware, prefix="/api/")

    @_app.get("/api/test")
    async def get_test(request: Request):
        return {
            "url": str(request.url),
            "base_url": str(request.base_url),
            "scheme": request.url.scheme,
            "netloc": request.url.netloc,
        }

    @_app.get("/other/test")
    async def get_other_test(request: Request):
        return {
            "url": str(request.url),
            "base_url": str(request.base_url),
        }

    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_middleware_rewrites_scope(client):
    with patch("app.middleware.ingress.get_public_ingress_base_url", new_callable=AsyncMock) as mock_get_url:
        mock_get_url.return_value = "https://public.example.com"

        response = client.get(
            "http://testserver/api/test",
            headers={"Host": "ingress.example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://public.example.com/api/test"
        assert data["base_url"] == "https://public.example.com/"
        assert data["scheme"] == "https"
        assert data["netloc"] == "public.example.com"
        mock_get_url.assert_awaited_once()


def test_middleware_ignores_other_paths(client):
    with patch("app.middleware.ingress.get_public_ingress_base_url", new_callable=AsyncMock) as mock_get_url:
        mock_get_url.return_value = "https://public.example.com"

        response = client.get("http://127.0.0.1:8000/other/test")
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "http://127.0.0.1:8000/other/test"
        assert data["base_url"] == "http://127.0.0.1:8000/"
        mock_get_url.assert_not_called()


def test_middleware_skips_private_lan_host(client):
    with patch("app.middleware.ingress.get_public_ingress_base_url", new_callable=AsyncMock) as mock_get_url:
        mock_get_url.return_value = "https://public.example.com"

        response = client.get("http://testserver/api/test", headers={"Host": "192.168.1.5:8000"})
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "http://192.168.1.5:8000/api/test"
        assert data["netloc"] == "192.168.1.5:8000"
        mock_get_url.assert_not_called()


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("192.168.0.10", True),
        ("10.0.0.5", True),
        ("172.16.1.2", True),
        ("public.example.com", False),
    ],
)
def test_should_skip_ingress_rewrite(host: str, expected: bool) -> None:
    assert should_skip_ingress_rewrite(host) is expected


def test_middleware_empty_url_does_not_rewrite(client):
    with patch("app.middleware.ingress.get_public_ingress_base_url", new_callable=AsyncMock) as mock_get_url:
        mock_get_url.return_value = ""

        response = client.get(
            "http://testserver/api/test",
            headers={"Host": "ingress.example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "http://ingress.example.com/api/test"
        assert data["base_url"] == "http://ingress.example.com/"
        mock_get_url.assert_awaited_once()


def test_middleware_skips_loopback_host(client):
    with patch("app.middleware.ingress.get_public_ingress_base_url", new_callable=AsyncMock) as mock_get_url:
        mock_get_url.return_value = "https://public.example.com"

        response = client.get("http://127.0.0.1:8000/api/test")
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "http://127.0.0.1:8000/api/test"
        mock_get_url.assert_not_called()
