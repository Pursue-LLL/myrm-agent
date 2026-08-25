"""
[INPUT]
- myrm_agent_harness.runtime.maintenance::detect_hardware_profile (POS: 跨平台硬件探针能力)
- app.api.integrations.model_specs::get_dynamic_model_specs (POS: Ollama 模型规格数据源)

[OUTPUT]
- get_hardware_recommendations: 获取基于硬件的 64K 上下文 KV Cache 显存透视、Reference Ladder 段位与模型推荐
- pull_ollama_model: 代理 Ollama 模型拉取并流式返回进度
- delete_ollama_model: 代理 Ollama 本地模型删除

[POS]
硬件推荐与本地模型管理 API。为前端 Settings Hardware Cookbook 提供硬件检测、64K KV 显存透视与 Ollama 本地模型管理能力。
"""

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.integrations.hardware_calculator import (
    _FIT_PRIORITY,
    calculate_kv_cache_vram_gb,
    derive_hardware_rung,
    estimate_tok_per_sec,
)
from app.api.integrations.model_specs import get_dynamic_model_specs
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_HARDWARE_PROFILE_CACHE: tuple[float, object] | None = None
_HARDWARE_PROFILE_LOCK = asyncio.Lock()


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
            response = await client.request(
                "DELETE",
                "http://localhost:11434/api/delete",
                json={"name": request.model_name},
            )
            if response.status_code == 200:
                return success_response(data={"success": True})
            else:
                logger.warning(
                    "Ollama delete failed (status %s): %s",
                    response.status_code,
                    response.text,
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Ollama model deletion failed",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ollama delete request failed: %s", e)
        raise HTTPException(status_code=500, detail="Ollama service unavailable") from e


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
                    "POST",
                    "http://localhost:11434/api/pull",
                    json={"name": request.model_name},
                ) as response:
                    if response.status_code != 200:
                        yield f'{{"error": "Ollama returned status {response.status_code}"}}\n'.encode("utf-8")
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except Exception as e:
            logger.error("Ollama model pull failed: %s", e)
            yield b'{"error": "Ollama model pull failed"}\n'

    return StreamingResponse(_stream_pull(), media_type="application/x-ndjson")


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
    available_vram_gb: float | None = Field(default=None, description="可用显存(GB)")
    current_rung: int | None = Field(default=None, description="硬件梯队Rung等级 (1-5)")
    rung_name: str | None = Field(default=None, description="梯队名称")

    ollama_running: bool = Field(default=False, description="本地 Ollama 是否正在运行")
    recommendations: list[dict[str, object]] = Field(default_factory=list, description="推荐模型列表")


@router.get("/recommendations", response_model=StandardSuccessResponse)
async def get_hardware_recommendations() -> JSONResponse:
    """
    获取基于本地硬件的模型推荐 (Fit Score) 与 64K 上下文 KV Cache 显存透视

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

    current_rung, rung_name = derive_hardware_rung(available_vram)
    bandwidth_gbps: float | None = getattr(profile, "memory_bandwidth_gbps", None)
    gpu_vendor: str = getattr(profile, "gpu_vendor", "unknown") or "unknown"

    recommendations = []
    for spec in model_specs:
        req_vram = float(spec["req_vram_gb"])
        params_b = float(spec.get("params_b", 0.0))
        active_params_b: float | None = float(spec["active_params_b"]) if spec.get("active_params_b") else None
        model_id = spec["id"]
        min_rung = int(spec.get("min_rung", 1))

        # 64K Context KV Cache VRAM calculations
        num_layers = int(spec.get("num_layers", 32))
        kv_heads = int(spec.get("kv_heads", 8))
        head_dim = int(spec.get("head_dim", 128))

        kv_fp16_64k = calculate_kv_cache_vram_gb(num_layers, kv_heads, head_dim, context_length=65536, bytes_per_elem=2.0)
        kv_q8_64k = calculate_kv_cache_vram_gb(num_layers, kv_heads, head_dim, context_length=65536, bytes_per_elem=1.0)
        kv_q4_64k = calculate_kv_cache_vram_gb(num_layers, kv_heads, head_dim, context_length=65536, bytes_per_elem=0.5)

        total_vram_64k_fp16 = round(req_vram + kv_fp16_64k, 2)
        total_vram_64k_q8 = round(req_vram + kv_q8_64k, 2)

        ollama_model_name = model_id.split("/")[-1] if "/" in model_id else model_id
        is_installed = ollama_model_name in installed_models

        # Evaluation considering 64k context total memory load
        if available_vram >= total_vram_64k_fp16:
            ratio = available_vram / total_vram_64k_fp16
            if ratio >= 1.6:
                score = 95
                fit_level = "perfect"
            elif ratio >= 1.2:
                score = 88
                fit_level = "good"
            else:
                score = 78
                fit_level = "good"
        elif available_vram >= total_vram_64k_q8:
            score = 72
            fit_level = "fair"
        elif available_vram >= req_vram:
            score = 55
            fit_level = "fair"
        else:
            ratio = available_vram / req_vram
            score = int(ratio * 40)
            fit_level = "poor"

        est_tok_per_sec = estimate_tok_per_sec(bandwidth_gbps, params_b, gpu_vendor, active_params_b) if params_b > 0 else None

        recommendations.append(
            {
                "model_id": model_id,
                "name": spec["name"],
                "description": spec["description"],
                "req_vram_gb": req_vram,
                "params_b": params_b,
                "disk_size_gb": spec.get("disk_size_gb"),
                "min_rung": min_rung,
                "num_layers": num_layers,
                "kv_heads": kv_heads,
                "head_dim": head_dim,
                "kv_fp16_64k_gb": kv_fp16_64k,
                "kv_q8_64k_gb": kv_q8_64k,
                "kv_q4_64k_gb": kv_q4_64k,
                "total_vram_64k_fp16_gb": total_vram_64k_fp16,
                "total_vram_64k_q8_gb": total_vram_64k_q8,
                "fit_score": score,
                "fit_level": fit_level,
                "is_installed": is_installed,
                "est_tok_per_sec": est_tok_per_sec,
            }
        )

    # Three-level sort: fit level (best first) → params_b desc → est_tok_per_sec desc.
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
        free_disk_gb=(round(getattr(profile, "free_disk_gb", 0.0), 1) if getattr(profile, "free_disk_gb", None) else None),
        has_gpu=getattr(profile, "has_gpu", False),
        gpu_name=getattr(profile, "gpu_name", None),
        gpu_vram_gb=(round(getattr(profile, "gpu_vram_gb", 0.0), 1) if getattr(profile, "gpu_vram_gb", None) else None),
        is_unified_memory=getattr(profile, "is_unified_memory", False),
        available_vram_gb=round(available_vram, 1),
        current_rung=current_rung,
        rung_name=rung_name,
        ollama_running=is_ollama_running,
        recommendations=recommendations,
    )

    return success_response(data=response.model_dump())
