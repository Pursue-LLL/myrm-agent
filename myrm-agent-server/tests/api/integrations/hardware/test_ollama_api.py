"""POST /integrations/hardware/ollama/pull and DELETE /integrations/hardware/ollama/models.

[POS]
tests/api/integrations/hardware/test_ollama_api.py

[INPUT]
- app.api.integrations.hardware.cookbook: the router, with the Ollama HTTP calls and the agentic Modelfile helper patched

[OUTPUT]
- Pins sandbox-mode refusal, the success path and the agentic Modelfile create/cleanup around pull and delete
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Import the router directly instead of the whole app to avoid FastAPI app initialization issues in tests
from app.api.integrations.hardware.cookbook import router as hardware_router
from app.config.deploy_mode import DeployMode

app = FastAPI()
app.include_router(hardware_router, prefix="/api/v1/integrations/hardware")


@pytest.mark.asyncio
async def test_ollama_delete_sandbox_mode():
    """Test that DELETE /hardware/ollama/models is forbidden in SANDBOX mode"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.SANDBOX):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.request(
                "DELETE",
                "/api/v1/integrations/hardware/ollama/models",
                json={"model_name": "test"},
            )
            assert response.status_code == 403


@pytest.mark.asyncio
async def test_ollama_delete_local_mode_success_proper_mock():
    """Test successful DELETE /hardware/ollama/models in local mode with proper mocking"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        # Instead of mocking httpx.AsyncClient.request globally which breaks the test client,
        # we mock it only for the specific call inside our route handler

        original_request = httpx.AsyncClient.request

        async def mock_request_func(self, method, url, **kwargs):
            if "localhost:11434" in str(url):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                return mock_resp
            return await original_request(self, method, url, **kwargs)

        with patch(
            "app.api.integrations.hardware.cookbook.httpx.AsyncClient.request",
            new=mock_request_func,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.request(
                    "DELETE",
                    "/api/v1/integrations/hardware/ollama/models",
                    json={"model_name": "test:latest"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["success"] is True


@pytest.mark.asyncio
async def test_ollama_pull_sandbox_mode():
    """Test that POST /hardware/ollama/pull is forbidden in SANDBOX mode"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.SANDBOX):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/integrations/hardware/ollama/pull", json={"model_name": "test"})
            assert response.status_code == 403


@pytest.mark.asyncio
async def test_ollama_pull_success_creates_agentic_modelfile():
    """Test that pull_ollama_model creates an agentic Modelfile after success chunk."""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware.cookbook._ensure_agentic_modelfile") as mock_ensure:
            mock_ensure.return_value = True

            # Mock httpx response stream for Ollama pull
            async def mock_stream_bytes():
                yield b'{"status": "pulling layer"}\n'
                yield b'{"status":"success"}\n'

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.aiter_bytes = mock_stream_bytes

            mock_client_instance = AsyncMock()
            mock_stream_ctx = MagicMock()
            mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.stream = MagicMock(return_value=mock_stream_ctx)

            with patch("httpx.AsyncClient", return_value=mock_client_instance):
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.post(
                        "/api/v1/integrations/hardware/ollama/pull",
                        json={"model_name": "qwen2.5:0.5b"},
                    )
                    assert response.status_code == 200
                    chunks = [line for line in response.text.split("\n") if line]
                    assert any("agentic_modelfile_created" in c for c in chunks)
                    mock_ensure.assert_called_once_with("qwen2.5:0.5b", num_ctx=64000)


@pytest.mark.asyncio
async def test_ollama_delete_cleans_agentic_model():
    """Test that delete_ollama_model deletes both base and -agentic model."""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.request(
                    "DELETE",
                    "/api/v1/integrations/hardware/ollama/models",
                    json={"model_name": "qwen2.5:0.5b"},
                )
                assert response.status_code == 200
                # Base model deletion + agentic model cleanup call
                assert mock_client.request.call_count == 2


@pytest.mark.asyncio
async def test_ollama_pull_failure_does_not_create_agentic_modelfile():
    """Edge case: Ollama pull failure stream should NOT trigger _ensure_agentic_modelfile."""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware.cookbook._ensure_agentic_modelfile") as mock_ensure:

            async def mock_stream_bytes():
                yield b'{"status": "pulling layer"}\n'
                yield b'{"error": "model not found"}\n'

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.aiter_bytes = mock_stream_bytes

            mock_client_instance = AsyncMock()
            mock_stream_ctx = MagicMock()
            mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_client_instance.stream = MagicMock(return_value=mock_stream_ctx)

            with patch("httpx.AsyncClient", return_value=mock_client_instance):
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)

                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.post(
                        "/api/v1/integrations/hardware/ollama/pull",
                        json={"model_name": "non_existent_model"},
                    )
                    assert response.status_code == 200
                    chunks = [line for line in response.text.split("\n") if line]
                    assert not any("agentic_modelfile_created" in c for c in chunks)
                    mock_ensure.assert_not_called()
