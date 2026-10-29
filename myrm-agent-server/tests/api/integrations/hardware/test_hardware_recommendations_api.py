"""GET /integrations/hardware/recommendations: deploy-mode gating, fit ranking, tokens/s and parameter counts.

[POS]
tests/api/integrations/hardware/test_hardware_recommendations_api.py

[INPUT]
- app.api.integrations.hardware.cookbook: the router, with the hardware profile, Ollama status and model specs patched

[OUTPUT]
- Pins the response of the recommendations endpoint in sandbox and local mode
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Import the router directly instead of the whole app to avoid FastAPI app initialization issues in tests
from app.api.integrations.hardware.cookbook import router as hardware_router
from app.config.deploy_mode import DeployMode

app = FastAPI()
app.include_router(hardware_router, prefix="/api/v1/integrations/hardware")


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
        with patch("app.api.integrations.hardware.cookbook._get_cached_hardware_profile") as mock_profile:
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

            with patch("app.api.integrations.hardware.cookbook._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (True, ["qwen2.5:0.5b"])

                with patch("app.api.integrations.hardware.cookbook.get_dynamic_model_specs") as mock_specs:
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
                        },
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
                        assert data["data"]["current_rung"] == 3  # 28GB available VRAM -> Rung 3
                        assert "High-end" in data["data"]["rung_name"]

                        recs = data["data"]["recommendations"]
                        assert len(recs) == 2

                        # Qwen 2.5 0.5B should be perfect fit (32-4 = 28GB available > 1.5GB)
                        assert recs[0]["model_id"] == "ollama/qwen2.5:0.5b"
                        assert recs[0]["fit_level"] == "perfect"
                        assert recs[0]["is_installed"] is True
                        assert recs[0]["disk_size_gb"] == 0.4
                        assert recs[0]["min_rung"] == 1
                        assert "kv_fp16_64k_gb" in recs[0]
                        assert "total_vram_64k_fp16_gb" in recs[0]
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
        with patch("app.api.integrations.hardware.cookbook._get_cached_hardware_profile") as mock_profile:
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

            with patch("app.api.integrations.hardware.cookbook._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (True, [])

                with patch("app.api.integrations.hardware.cookbook.get_dynamic_model_specs") as mock_specs:
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
async def test_hardware_recommendations_sorting_same_fit_level_largest_params_first():
    """Within same fit_level, largest params_b model ranks first."""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware.cookbook._get_cached_hardware_profile") as mock_profile:
            mock_profile_obj = MagicMock()
            mock_profile_obj.os_type = "macos"
            mock_profile_obj.cpu_arch = "arm64"
            mock_profile_obj.total_ram_gb = 64.0
            mock_profile_obj.free_disk_gb = 200.0
            mock_profile_obj.has_gpu = True
            mock_profile_obj.gpu_name = "Apple M2 Max"
            mock_profile_obj.gpu_vram_gb = 64.0
            mock_profile_obj.is_unified_memory = True
            mock_profile_obj.gpu_vendor = "apple"
            mock_profile_obj.memory_bandwidth_gbps = 400.0
            mock_profile.return_value = mock_profile_obj

            with patch("app.api.integrations.hardware.cookbook._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (False, [])

                with patch("app.api.integrations.hardware.cookbook.get_dynamic_model_specs") as mock_specs:
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
                            "id": "ollama/qwen3:8b",
                            "name": "Qwen 3 (8B)",
                            "description": "Test",
                            "req_vram_gb": 6.0,
                            "params_b": 8.0,
                            "disk_size_gb": 4.9,
                        },
                    ]

                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                        response = await ac.get("/api/v1/integrations/hardware/recommendations")
                        assert response.status_code == 200
                        data = response.json()
                        recs = data["data"]["recommendations"]

                        assert len(recs) == 2
                        # 60GB available: both 0.5B (1.5+1.5) and 8B (6+8) have ratio > 1.6 -> both 'perfect'
                        assert recs[0]["fit_level"] == "perfect"
                        assert recs[1]["fit_level"] == "perfect"
                        # 8B has higher params_b than 0.5B -> ranks first
                        assert recs[0]["model_id"] == "ollama/qwen3:8b"
                        assert recs[1]["model_id"] == "ollama/qwen2.5:0.5b"


@pytest.mark.asyncio
async def test_hardware_recommendations_moe_tps_uses_active_params():
    """DeepSeek R1 32B (MoE) should show accurate TPS using active_params_b=7.0.

    On RTX 4090 (1008 GBps, nvidia):
      With wrong params_b=32:   ~31 tok/s  (misleads user as RED/slow)
      With active_params_b=7:   ~141 tok/s (accurate, user sees GREEN/fast)
    """
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware.cookbook._get_cached_hardware_profile") as mock_profile:
            mock_profile_obj = MagicMock()
            mock_profile_obj.os_type = "windows"
            mock_profile_obj.cpu_arch = "AMD64"
            mock_profile_obj.total_ram_gb = 64.0
            mock_profile_obj.free_disk_gb = 500.0
            mock_profile_obj.has_gpu = True
            mock_profile_obj.gpu_name = "NVIDIA GeForce RTX 4090"
            mock_profile_obj.gpu_vram_gb = 24.0
            mock_profile_obj.is_unified_memory = False
            mock_profile_obj.gpu_vendor = "nvidia"
            mock_profile_obj.memory_bandwidth_gbps = 1008.0  # RTX 4090
            mock_profile.return_value = mock_profile_obj

            with patch("app.api.integrations.hardware.cookbook._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (True, ["deepseek-r1:32b"])

                with patch("app.api.integrations.hardware.cookbook.get_dynamic_model_specs") as mock_specs:
                    mock_specs.return_value = [
                        {
                            "id": "ollama/deepseek-r1:32b",
                            "name": "DeepSeek R1 (32B)",
                            "description": "Test",
                            "req_vram_gb": 22.0,
                            "params_b": 32.0,
                            "active_params_b": 7.0,
                            "disk_size_gb": 20.0,
                        }
                    ]

                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                        response = await ac.get("/api/v1/integrations/hardware/recommendations")
                        assert response.status_code == 200
                        data = response.json()
                        recs = data["data"]["recommendations"]

                        assert len(recs) == 1
                        rec = recs[0]
                        assert rec["model_id"] == "ollama/deepseek-r1:32b"
                        assert rec["fit_level"] in ("perfect", "good", "fair")
                        # active_params_b=7 is used → TPS >> 31 (what wrong params_b=32 would give)
                        assert rec["est_tok_per_sec"] is not None
                        assert rec["est_tok_per_sec"] > 50, (
                            f"MoE model TPS ({rec['est_tok_per_sec']}) should be >50 using "
                            "active_params_b=7, not ~31 from total params_b=32"
                        )
                        assert rec["est_tok_per_sec"] > 100  # Expected ~141 tok/s


@pytest.mark.asyncio
async def test_hardware_recommendations_params_b_in_response():
    """params_b must be present in every recommendation item (required for sorting)."""
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("app.api.integrations.hardware.cookbook._get_cached_hardware_profile") as mock_profile:
            mock_profile_obj = MagicMock()
            mock_profile_obj.os_type = "linux"
            mock_profile_obj.cpu_arch = "x86_64"
            mock_profile_obj.total_ram_gb = 32.0
            mock_profile_obj.free_disk_gb = 100.0
            mock_profile_obj.has_gpu = True
            mock_profile_obj.gpu_name = "NVIDIA GeForce RTX 3080"
            mock_profile_obj.gpu_vram_gb = 10.0
            mock_profile_obj.is_unified_memory = False
            mock_profile_obj.gpu_vendor = "nvidia"
            mock_profile_obj.memory_bandwidth_gbps = 760.0  # RTX 3080
            mock_profile.return_value = mock_profile_obj

            with patch("app.api.integrations.hardware.cookbook._get_ollama_status") as mock_ollama:
                mock_ollama.return_value = (False, [])

                with patch("app.api.integrations.hardware.cookbook.get_dynamic_model_specs") as mock_specs:
                    mock_specs.return_value = [
                        {
                            "id": "ollama/qwen3:8b",
                            "name": "Qwen 3 (8B)",
                            "description": "Test",
                            "req_vram_gb": 6.0,
                            "params_b": 8.0,
                            "disk_size_gb": 4.9,
                        },
                        {
                            "id": "ollama/qwen2.5:14b",
                            "name": "Qwen 2.5 (14B)",
                            "description": "Test",
                            "req_vram_gb": 10.0,
                            "params_b": 14.0,
                            "disk_size_gb": 9.0,
                        },
                    ]

                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                        response = await ac.get("/api/v1/integrations/hardware/recommendations")
                        assert response.status_code == 200
                        data = response.json()
                        recs = data["data"]["recommendations"]

                        for rec in recs:
                            assert "params_b" in rec, f"params_b missing from {rec['model_id']}"
                            assert isinstance(rec["params_b"], (int, float))
                            assert rec["params_b"] > 0
