import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_HARDWARE_PROFILE_CACHE: tuple[float, object] | None = None
_HARDWARE_PROFILE_LOCK = asyncio.Lock()

_MODEL_SPECS_CACHE: tuple[float, list[dict[str, object]]] | None = None
_MODEL_SPECS_LOCK = asyncio.Lock()

_FALLBACK_MODEL_SPECS = [
    {
        "id": "ollama/qwen2.5:0.5b",
        "name": "Qwen 2.5 (0.5B)",
        "description": "极速响应，适合简单任务和低配机器",
        "req_vram_gb": 1.5,
        "params_b": 0.5,
    },
    {
        "id": "ollama/qwen2.5:3b",
        "name": "Qwen 2.5 (3B)",
        "description": "速度与能力的良好平衡，适合主流轻薄本",
        "req_vram_gb": 3.0,
        "params_b": 3.0,
    },
    {
        "id": "ollama/llama3.2:8b",
        "name": "Llama 3.2 (8B)",
        "description": "强大的通用模型，适合主流开发机",
        "req_vram_gb": 6.0,
        "params_b": 8.0,
    },
    {
        "id": "ollama/qwen2.5:14b",
        "name": "Qwen 2.5 (14B)",
        "description": "极强的推理能力，适合高配工作站",
        "req_vram_gb": 10.0,
        "params_b": 14.0,
    },
    {
        "id": "ollama/deepseek-r1:32b",
        "name": "DeepSeek R1 (32B)",
        "description": "专家级推理模型，需要顶级硬件",
        "req_vram_gb": 22.0,
        "params_b": 32.0,
    },
    {
        "id": "ollama/llama3.1:70b",
        "name": "Llama 3.1 (70B)",
        "description": "超大规模模型，仅限顶级工作站",
        "req_vram_gb": 40.0,
        "params_b": 70.0,
    },
]


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


async def _get_dynamic_model_specs() -> list[dict[str, object]]:
    """动态拉取模型规格字典（带本地 Fallback）"""
    global _MODEL_SPECS_CACHE
    now = time.monotonic()

    if _MODEL_SPECS_CACHE and (now - _MODEL_SPECS_CACHE[0]) < 3600.0:
        return _MODEL_SPECS_CACHE[1]

    async with _MODEL_SPECS_LOCK:
        if _MODEL_SPECS_CACHE and (now - _MODEL_SPECS_CACHE[0]) < 3600.0:
            return _MODEL_SPECS_CACHE[1]

        specs = _FALLBACK_MODEL_SPECS
        try:
            # 尝试从云端拉取，设置 3 秒超时
            async with httpx.AsyncClient(timeout=3.0) as client:
                # 使用 GitHub Raw 作为默认的云端配置源
                response = await client.get(
                    "https://raw.githubusercontent.com/yululiu/open-perplexity/main/myrm-agent-brand/myrm-website/public/cookbook_specs.json"
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        specs = data
        except Exception as e:
            logger.warning(f"Failed to fetch dynamic model specs, using fallback: {e}")

        _MODEL_SPECS_CACHE = (now, specs)
        return specs


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


@router.delete("/hardware/ollama/models")
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hardware/ollama/pull")
async def pull_ollama_model(request: OllamaPullRequest) -> StreamingResponse:
    """代理 Ollama 的 /api/pull 接口，返回流式进度"""
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() == DeployMode.SANDBOX:
        raise HTTPException(status_code=403, detail="Not available in SaaS mode")

    async def _stream_pull():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
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


@router.get("/hardware/recommendations", response_model=StandardSuccessResponse)
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

    model_specs = await _get_dynamic_model_specs()
    is_ollama_running, installed_models = await _get_ollama_status()

    available_vram = 0.0
    if getattr(profile, "is_unified_memory", False):
        available_vram = max(0.0, getattr(profile, "total_ram_gb", 0.0) - 4.0)
    elif getattr(profile, "has_gpu", False) and getattr(profile, "gpu_vram_gb", None):
        available_vram = getattr(profile, "gpu_vram_gb", 0.0)
    else:
        available_vram = getattr(profile, "total_ram_gb", 0.0) * 0.5

    recommendations = []
    for spec in model_specs:
        req_vram = float(spec["req_vram_gb"])
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

        recommendations.append(
            {
                "model_id": model_id,
                "name": spec["name"],
                "description": spec["description"],
                "req_vram_gb": req_vram,
                "fit_score": score,
                "fit_level": fit_level,
                "is_installed": is_installed,
            }
        )

    recommendations.sort(key=lambda x: int(x["fit_score"]), reverse=True)

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
