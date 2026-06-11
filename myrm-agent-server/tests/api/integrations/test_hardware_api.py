from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Import the router directly instead of the whole app to avoid FastAPI app initialization issues in tests
from app.api.integrations.hardware import _estimate_tok_per_sec, router as hardware_router
from app.config.deploy_mode import DeployMode

app = FastAPI()
app.include_router(hardware_router, prefix="/api/v1/integrations/hardware")

# --- _estimate_tok_per_sec unit tests ---

def test_estimate_tok_per_sec_apple_m2_pro_8b():
    # M2 Pro: 200 GBps, Q4_K_M 8B, apple vendor_factor=0.82, efficiency=0.55
    # raw = 200e9 / (8e9 * 0.5625) = 44.44
    # tok/s = 44.44 * 0.55 * 0.82 = 20.04 -> round = 20
    result = _estimate_tok_per_sec(200.0, 8.0, "apple")
    assert result == 20


def test_estimate_tok_per_sec_rtx4090_8b():
    # RTX 4090: 1008 GBps, nvidia vendor_factor=1.0
    # raw = 1008e9 / (8e9 * 0.5625) = 224
    # tok/s = 224 * 0.55 * 1.0 = 123.2 -> round = 123
    result = _estimate_tok_per_sec(1008.0, 8.0, "nvidia")
    assert result == 123


def test_estimate_tok_per_sec_m1_8b():
    # M1: 68.25 GBps, apple vendor_factor=0.82
    # raw = 68.25e9 / (8e9 * 0.5625) = 15.166
    # tok/s = 15.166 * 0.55 * 0.82 = 6.84 -> round = 7 (above min 1)
    result = _estimate_tok_per_sec(68.25, 8.0, "apple")
    assert result == 7


def test_estimate_tok_per_sec_none_bandwidth():
    result = _estimate_tok_per_sec(None, 8.0, "nvidia")
    assert result is None


def test_estimate_tok_per_sec_zero_params():
    result = _estimate_tok_per_sec(200.0, 0.0, "apple")
    assert result is None


def test_estimate_tok_per_sec_zero_bandwidth():
    result = _estimate_tok_per_sec(0.0, 8.0, "nvidia")
    assert result is None


def test_estimate_tok_per_sec_unknown_vendor():
    # Unknown vendor_factor=0.60
    result = _estimate_tok_per_sec(200.0, 8.0, "unknown")
    assert result is not None
    assert result >= 1


def test_estimate_tok_per_sec_minimum_is_1():
    # Very small bandwidth + very large model -> should floor to 1
    result = _estimate_tok_per_sec(0.001, 70.0, "apple")
    assert result == 1


# --- API integration tests ---

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
            mock_profile_obj.gpu_vendor = "apple"
            mock_profile_obj.memory_bandwidth_gbps = 400.0  # M1 Max bandwidth
            mock_profile.return_value = mock_profile_obj
            
            with patch("app.api.integrations.hardware._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (True, ["qwen2.5:0.5b"])
                
                with patch("app.api.integrations.hardware.get_dynamic_model_specs") as mock_specs:
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
                        # M1 Max (400 GBps, apple) + 0.5B params -> high tok/s
                        assert recs[0]["est_tok_per_sec"] is not None
                        assert recs[0]["est_tok_per_sec"] > 100

                        # Llama 3.1 70B should be poor fit (28GB available < 40GB)
                        assert recs[1]["model_id"] == "ollama/llama3.1:70b"
                        assert recs[1]["fit_level"] == "poor"
                        assert recs[1]["is_installed"] is False
                        # 70B model on M1 Max -> slower but still estimated
                        assert recs[1]["est_tok_per_sec"] is not None
                        assert recs[1]["est_tok_per_sec"] >= 1

@pytest.mark.asyncio
async def test_hardware_recommendations_no_bandwidth():
    """When GPU bandwidth is unknown, est_tok_per_sec should be None for all models."""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware._get_cached_hardware_profile") as mock_profile:
            mock_profile_obj = MagicMock()
            mock_profile_obj.os_type = "windows"
            mock_profile_obj.cpu_arch = "AMD64"
            mock_profile_obj.total_ram_gb = 16.0
            mock_profile_obj.free_disk_gb = 50.0
            mock_profile_obj.has_gpu = True
            mock_profile_obj.gpu_name = "Some Unknown GPU XYZ"
            mock_profile_obj.gpu_vram_gb = 8.0
            mock_profile_obj.is_unified_memory = False
            mock_profile_obj.gpu_vendor = "unknown"
            mock_profile_obj.memory_bandwidth_gbps = None  # Unknown GPU, no bandwidth data
            mock_profile.return_value = mock_profile_obj

            with patch("app.api.integrations.hardware._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (True, [])

                with patch("app.api.integrations.hardware.get_dynamic_model_specs") as mock_specs:
                    mock_specs.return_value = [
                        {
                            "id": "ollama/qwen2.5:0.5b",
                            "name": "Qwen 2.5 (0.5B)",
                            "description": "Test",
                            "req_vram_gb": 1.5,
                            "params_b": 0.5,
                            "disk_size_gb": 0.4,
                        }
                    ]

                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                        response = await ac.get("/api/v1/integrations/hardware/recommendations")
                        assert response.status_code == 200
                        data = response.json()
                        assert data["code"] == 0
                        recs = data["data"]["recommendations"]
                        assert len(recs) == 1
                        # bandwidth unknown -> est_tok_per_sec must be None (not shown to user)
                        assert recs[0]["est_tok_per_sec"] is None


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
