"""
[INPUT]
- httpx::AsyncClient (POS: 调用方提供的 HTTP 客户端，决定超时与传输)

[OUTPUT]
- OLLAMA_PROBE_TIMEOUT_S: 单次探测请求的超时秒数
- OllamaModel: `/api/tags` 中的一条已安装模型
- list_ollama_models: 读取本机 Ollama 已安装模型，守护进程不可达时返回 None
- find_chat_model: 在已安装模型中找出首个既能对话又支持工具调用的本机模型

[POS]
本机 Ollama 守护进程探测。Cookbook 的"是否已安装"判断与首页一键连接共用同一份 `/api/tags` 读取，
一键连接再用 `/api/show` 的 capabilities 排除 embedding 模型、无工具调用能力的模型与云端转发模型。
"""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx

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
