import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.integrations.model_specs import get_dynamic_model_specs
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_HARDWARE_PROFILE_CACHE: tuple[float, object] | None = None
_HARDWARE_PROFILE_LOCK = asyncio.Lock()

# Bytes per weight for Q4_K_M quantization (dominant Ollama default format).
# GGUF spec: 4-bit quant ≈ 0.5 B/W + K-quant overhead → 0.5625 B/W.
_Q4_K_M_BYTES_PER_WEIGHT: float = 0.5625

# Empirical efficiency: real-world throughput vs. theoretical peak bandwidth.
# Accounts for KV cache I/O, CPU-GPU sync, tokenizer, and framework overhead.
_EFFICIENCY: float = 0.55

# Vendor-specific calibration from community benchmark data.
# Apple's tight memory controller yields ~82% of theoretical; AMD ROCm and
# Intel Arc carry higher driver overhead than NVIDIA CUDA.
_VENDOR_FACTOR: dict[str, float] = {
    "apple": 0.82,
    "nvidia": 1.00,
    "amd": 0.78,
    "intel": 0.65,
    "unknown": 0.60,
}

# Numeric priority for each fit level used in multi-key recommendation sort.
_FIT_PRIORITY: dict[str, int] = {"perfect": 3, "good": 2, "fair": 1, "poor": 0}


async def _get_cached_hardware_profile() -> object | None:
    """获取硬件探针结果（带内存缓存，避免阻塞事件循环）"""
    global _HARDWARE_PROFILE_CACHE
    now = time.monotonic()

    if _HARDWARE_PROFILE_CACHE and (now - _HARDWARE_PROFILE_CACHE[0]) < 3600.0:
        return _HARDWARE_PROFILE_CACHE[1]

    async with _HARDWARE_PROFILE_LOCK:
        if _HARDWARE_PROFILE_CACHE and (now - _HARDWARE_PROFILE_CACHE[0]) < 3600.0:
            return _HARDWARE_PROFILE_CACHE[1]

        from myrm_agent_harness.runtime.maintenance import detect_hardware_profile

        profile = await asyncio.to_thread(detect_hardware_profile)
        _HARDWARE_PROFILE_CACHE = (now, profile)
        return profile


async def _get_ollama_status() -> tuple[bool, list[str]]:
    """探测 Ollama 状态并获取已安装模型列表"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get("http://localhost:11434/api/tags")
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name") for m in data.get("models", []) if "name" in m]
                return True, models
    except Exception:
        pass
    return False, []


class OllamaPullRequest(BaseModel):
    model_name: str = Field(..., description="Ollama 模型名称，例如 qwen2.5:0.5b")


class OllamaDeleteRequest(BaseModel):
    model_name: str = Field(..., description="Ollama 模型名称，例如 qwen2.5:0.5b")


@router.delete("/ollama/models")
async def delete_ollama_model(request: OllamaDeleteRequest) -> JSONResponse:
    """代理 Ollama 的 /api/delete 接口"""
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() == DeployMode.SANDBOX:
        raise HTTPException(status_code=403, detail="Not available in SaaS mode")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request("DELETE", "http://localhost:11434/api/delete", json={"name": request.model_name})
            if response.status_code == 200:
                return success_response(data={"success": True})
            else:
                raise HTTPException(status_code=response.status_code, detail=f"Ollama error: {response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ollama/pull")
async def pull_ollama_model(request: OllamaPullRequest) -> StreamingResponse:
    """代理 Ollama 的 /api/pull 接口，返回流式进度"""
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() == DeployMode.SANDBOX:
        raise HTTPException(status_code=403, detail="Not available in SaaS mode")

    async def _stream_pull():
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST", "http://localhost:11434/api/pull", json={"name": request.model_name}
                ) as response:
                    if response.status_code != 200:
                        yield f'{{"error": "Ollama returned status {response.status_code}"}}\n'.encode("utf-8")
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except Exception as e:
            yield f'{{"error": "{str(e)}"}}\n'.encode("utf-8")

    return StreamingResponse(_stream_pull(), media_type="application/x-ndjson")


def _estimate_tok_per_sec(
    bandwidth_gbps: float | None,
    params_b: float,
    vendor: str,
    active_params_b: float | None = None,
) -> int | None:
    """Estimate inference throughput (tokens/s) for a Q4_K_M quantized LLM.

    Formula:  tok/s = (bandwidth_GBps * 1e9) / (effective_b * 1e9 * bytes_per_weight)
                       * efficiency * vendor_factor

    For MoE models (e.g. DeepSeek R1 32B which activates ~7B weights per token),
    pass ``active_params_b`` to use the number of *active* weights instead of the
    total model size.  VRAM/disk sizing still uses full ``params_b``; only the
    inference throughput estimate uses active weights.

    Returns None when bandwidth is unavailable (GPU not in lookup table).
    """
    if bandwidth_gbps is None or bandwidth_gbps <= 0 or params_b <= 0:
        return None
    # MoE models: inference cost scales with active parameters, not total
    effective_b = active_params_b if (active_params_b and active_params_b > 0) else params_b
    raw = (bandwidth_gbps * 1e9) / (effective_b * 1e9 * _Q4_K_M_BYTES_PER_WEIGHT)
    vendor_factor = _VENDOR_FACTOR.get(vendor, _VENDOR_FACTOR["unknown"])
    # Return integer tok/s — sub-1 precision is noise given ~15% estimation error
    return max(1, round(raw * _EFFICIENCY * vendor_factor))


class HardwareRecommendationResponse(BaseModel):
    """硬件推荐响应"""

    hardware_detected: bool = Field(..., description="是否成功检测到硬件")
    os_type: str | None = Field(default=None, description="操作系统类型")
    cpu_arch: str | None = Field(default=None, description="CPU架构")
    total_ram_gb: float | None = Field(default=None, description="总内存(GB)")
    free_disk_gb: float | None = Field(default=None, description="剩余磁盘空间(GB)")
    has_gpu: bool | None = Field(default=None, description="是否有GPU")
    gpu_name: str | None = Field(default=None, description="GPU名称")
    gpu_vram_gb: float | None = Field(default=None, description="GPU显存(GB)")
    is_unified_memory: bool | None = Field(default=None, description="是否为统一内存(如Apple Silicon)")

    ollama_running: bool = Field(default=False, description="本地 Ollama 是否正在运行")
    recommendations: list[dict[str, object]] = Field(default_factory=list, description="推荐模型列表")


@router.get("/recommendations", response_model=StandardSuccessResponse)
async def get_hardware_recommendations() -> JSONResponse:
    """
    获取基于本地硬件的模型推荐 (Fit Score)

    在 SaaS 模式下，或硬件检测失败时，返回 hardware_detected=False
    """
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() == DeployMode.SANDBOX:
        return success_response(data=HardwareRecommendationResponse(hardware_detected=False).model_dump())

    profile = await _get_cached_hardware_profile()
    if not profile:
        return success_response(data=HardwareRecommendationResponse(hardware_detected=False).model_dump())

    model_specs = await get_dynamic_model_specs()
    is_ollama_running, installed_models = await _get_ollama_status()

    available_vram = 0.0
    if getattr(profile, "is_unified_memory", False):
        available_vram = max(0.0, getattr(profile, "total_ram_gb", 0.0) - 4.0)
    elif getattr(profile, "has_gpu", False) and getattr(profile, "gpu_vram_gb", None):
        available_vram = getattr(profile, "gpu_vram_gb", 0.0)
    else:
        available_vram = getattr(profile, "total_ram_gb", 0.0) * 0.5

    bandwidth_gbps: float | None = getattr(profile, "memory_bandwidth_gbps", None)
    gpu_vendor: str = getattr(profile, "gpu_vendor", "unknown") or "unknown"

    recommendations = []
    for spec in model_specs:
        req_vram = float(spec["req_vram_gb"])
        params_b = float(spec.get("params_b", 0.0))
        active_params_b: float | None = float(spec["active_params_b"]) if spec.get("active_params_b") else None
        model_id = spec["id"]

        ollama_model_name = model_id.split("/")[-1] if "/" in model_id else model_id
        is_installed = ollama_model_name in installed_models

        if available_vram >= req_vram:
            ratio = available_vram / req_vram
            if ratio >= 2.0:
                score = 95
                fit_level = "perfect"
            elif ratio >= 1.5:
                score = 85
                fit_level = "good"
            else:
                score = 75
                fit_level = "fair"
        else:
            ratio = available_vram / req_vram
            score = int(ratio * 50)
            fit_level = "poor"

        est_tok_per_sec = (
            _estimate_tok_per_sec(bandwidth_gbps, params_b, gpu_vendor, active_params_b)
            if params_b > 0
            else None
        )

        recommendations.append(
            {
                "model_id": model_id,
                "name": spec["name"],
                "description": spec["description"],
                "req_vram_gb": req_vram,
                "params_b": params_b,
                "disk_size_gb": spec.get("disk_size_gb"),
                "fit_score": score,
                "fit_level": fit_level,
                "is_installed": is_installed,
                "est_tok_per_sec": est_tok_per_sec,
            }
        )

    # Three-level sort: fit level (best first) → params_b desc → est_tok_per_sec desc.
    # Within the same fit level, recommend the most capable (largest) model first,
    # then break remaining ties by raw throughput speed.
    recommendations.sort(
        key=lambda x: (
            _FIT_PRIORITY.get(str(x["fit_level"]), 0),
            x["params_b"],
            x["est_tok_per_sec"] or 0,
        ),
        reverse=True,
    )

    response = HardwareRecommendationResponse(
        hardware_detected=True,
        os_type=getattr(profile, "os_type", None),
        cpu_arch=getattr(profile, "cpu_arch", None),
        total_ram_gb=round(getattr(profile, "total_ram_gb", 0.0), 1),
        free_disk_gb=round(getattr(profile, "free_disk_gb", 0.0), 1) if getattr(profile, "free_disk_gb", None) else None,
        has_gpu=getattr(profile, "has_gpu", False),
        gpu_name=getattr(profile, "gpu_name", None),
        gpu_vram_gb=round(getattr(profile, "gpu_vram_gb", 0.0), 1) if getattr(profile, "gpu_vram_gb", None) else None,
        is_unified_memory=getattr(profile, "is_unified_memory", False),
        ollama_running=is_ollama_running,
        recommendations=recommendations,
    )

    return success_response(data=response.model_dump())
