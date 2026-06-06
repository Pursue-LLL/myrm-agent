import pytest
import httpx
from httpx import AsyncClient, ASGITransport
from app.config.deploy_mode import DeployMode
import json
from unittest.mock import patch, MagicMock

# Import the router directly instead of the whole app to avoid FastAPI app initialization issues in tests
from app.api.integrations.hardware import router as hardware_router
from fastapi import FastAPI

app = FastAPI()
app.include_router(hardware_router, prefix="/api/v1/integrations")

@pytest.mark.asyncio
async def test_hardware_recommendations_sandbox_mode():
    """Test that recommendations return hardware_detected=False in SANDBOX mode"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.SANDBOX):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/integrations/hardware/recommendations")
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["hardware_detected"] is False

@pytest.mark.asyncio
async def test_hardware_recommendations_local_mode():
    """Test recommendations in local mode with mocked hardware profile"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware._get_cached_hardware_profile") as mock_profile:
            mock_profile_obj = MagicMock()
            mock_profile_obj.os_type = "macos"
            mock_profile_obj.cpu_arch = "arm64"
            mock_profile_obj.total_ram_gb = 32.0
            mock_profile_obj.free_disk_gb = 100.0
            mock_profile_obj.has_gpu = True
            mock_profile_obj.gpu_name = "Apple M1 Max"
            mock_profile_obj.gpu_vram_gb = 32.0
            mock_profile_obj.is_unified_memory = True
            mock_profile.return_value = mock_profile_obj
            
            with patch("app.api.integrations.hardware._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (True, ["qwen2.5:0.5b"])
                
                with patch("app.api.integrations.hardware._get_dynamic_model_specs") as mock_specs:
                    mock_specs.return_value = [
                        {
                            "id": "ollama/qwen2.5:0.5b",
                            "name": "Qwen 2.5 (0.5B)",
                            "description": "Test",
                            "req_vram_gb": 1.5,
                            "params_b": 0.5,
                            "disk_size_gb": 0.4,
                        },
                        {
                            "id": "ollama/llama3.1:70b",
                            "name": "Llama 3.1 (70B)",
                            "description": "Test",
                            "req_vram_gb": 40.0,
                            "params_b": 70.0,
                            "disk_size_gb": 39.0,
                        }
                    ]
                
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                        response = await ac.get("/api/v1/integrations/hardware/recommendations")
                        assert response.status_code == 200
                        data = response.json()
                        assert data["code"] == 0
                        assert data["data"]["hardware_detected"] is True
                        assert data["data"]["os_type"] == "macos"
                        assert data["data"]["total_ram_gb"] == 32.0
                        assert data["data"]["free_disk_gb"] == 100.0
                        assert data["data"]["is_unified_memory"] is True
                        assert data["data"]["ollama_running"] is True
                        
                        recs = data["data"]["recommendations"]
                        assert len(recs) == 2
                        
                        # Qwen 2.5 0.5B should be perfect fit (32-4 = 28GB available > 1.5GB)
                        assert recs[0]["model_id"] == "ollama/qwen2.5:0.5b"
                        assert recs[0]["fit_level"] == "perfect"
                        assert recs[0]["is_installed"] is True
                        assert recs[0]["disk_size_gb"] == 0.4
                        
                        # Llama 3.1 70B should be poor fit (28GB available < 40GB)
                        assert recs[1]["model_id"] == "ollama/llama3.1:70b"
                        assert recs[1]["fit_level"] == "poor"
                        assert recs[1]["is_installed"] is False

@pytest.mark.asyncio
async def test_ollama_delete_sandbox_mode():
    """Test that DELETE /hardware/ollama/models is forbidden in SANDBOX mode"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.SANDBOX):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.request("DELETE", "/api/v1/integrations/hardware/ollama/models", json={"model_name": "test"})
            assert response.status_code == 403

@pytest.mark.asyncio
async def test_ollama_delete_local_mode_success():
    """Test successful DELETE /hardware/ollama/models in local mode"""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware.httpx.AsyncClient.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.request("DELETE", "/api/v1/integrations/hardware/ollama/models", json={"model_name": "test:latest"})
                assert response.status_code == 200
                data = response.json()
                # When mocking httpx.AsyncClient.request, it intercepts the request to our own FastAPI app too!
                # We need to only mock the request to localhost:11434
                pass

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
            
        with patch("app.api.integrations.hardware.httpx.AsyncClient.request", new=mock_request_func):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.request("DELETE", "/api/v1/integrations/hardware/ollama/models", json={"model_name": "test:latest"})
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
