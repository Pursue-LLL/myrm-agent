"""
[INPUT]
- httpx::AsyncClient (POS: 调用方提供的 HTTP 客户端，决定超时与传输)
- app.services.config.onboarding::get_ollama_base_url (POS: 本机 Ollama 守护进程地址的唯一解析入口)

[OUTPUT]
- OLLAMA_PROBE_TIMEOUT_S: 单次探测请求的超时秒数
- OllamaModel: `/api/tags` 中的一条已安装模型
- list_ollama_models: 读取本机 Ollama 已安装模型，守护进程不可达时返回 None
- find_chat_model: 在已安装模型中找出首个既能对话又支持工具调用的本机模型
- router: `GET /chat-model`，为首页"使用本机 Ollama"一键连接挑出可用模型

[POS]
本机 Ollama 探测与一键连接端点。只读取用户已经装好的模型，不安装、不下载、不评估硬件。
"""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.config.onboarding import get_ollama_base_url

router = APIRouter()

OLLAMA_PROBE_TIMEOUT_S = 2.0

# 只核对列表靠前的模型：首个合格模型通常就在最前面，逐个 /api/show 的总耗时因此有上限。
_MAX_CAPABILITY_CHECKS = 5
_REQUIRED_CAPABILITIES = frozenset({"completion", "tools"})


@dataclass(frozen=True, slots=True)
class OllamaModel:
    name: str
    # 云端转发模型（带 remote_host / remote_model）会把对话发往本机以外，不属于"本机 Ollama"。
    is_remote: bool


async def list_ollama_models(client: httpx.AsyncClient, base_url: str) -> list[OllamaModel] | None:
    """Return the installed models in the daemon's listing order, or None when the daemon cannot be reached."""
    try:
        response = await client.get(f"{base_url}/api/tags")
        if response.status_code != 200:
            return None
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return None
    return [
        OllamaModel(name=entry["name"], is_remote=bool(entry.get("remote_host") or entry.get("remote_model")))
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]


async def find_chat_model(client: httpx.AsyncClient, base_url: str, models: Sequence[OllamaModel]) -> str | None:
    """Return the first local model that can chat and call tools, or None when none is known to.

    `/api/show` reports what a model can do under `capabilities`. Older daemons omit the field, and an omitted
    field counts as unknown rather than capable: connecting a model that cannot call tools breaks the first chat.
    """
    for model in [m for m in models if not m.is_remote][:_MAX_CAPABILITY_CHECKS]:
        try:
            response = await client.post(f"{base_url}/api/show", json={"model": model.name})
            if response.status_code != 200:
                continue
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            continue

        capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
        if isinstance(capabilities, list) and all(capability in capabilities for capability in _REQUIRED_CAPABILITIES):
            return model.name
    return None


class OllamaChatModelResponse(BaseModel):
    model: str | None = Field(default=None, description="能对话且支持工具调用的本机模型；没有合格模型时为空")
    base_url: str = Field(..., description="探测所用的 Ollama 地址，连接时作为该 provider 的 API 地址")


@router.get("/chat-model", response_model=StandardSuccessResponse)
async def get_ollama_chat_model() -> JSONResponse:
    """给首页一键连接挑出本机 Ollama 里首个能对话且支持工具调用的模型。

    Ollama 未运行、没有合格模型、或守护进程版本过旧（不报告 capabilities）时 model 为空，前端据此不显示按钮。
    """
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() == DeployMode.SANDBOX:
        raise HTTPException(status_code=403, detail="Not available in SaaS mode")

    base_url = get_ollama_base_url()
    async with httpx.AsyncClient(timeout=OLLAMA_PROBE_TIMEOUT_S) as client:
        models = await list_ollama_models(client, base_url)
        chat_model = await find_chat_model(client, base_url, models) if models else None
    return success_response(data=OllamaChatModelResponse(model=chat_model, base_url=base_url).model_dump())
