"""
[INPUT]
- httpx::AsyncClient (POS: 调用方提供的 HTTP 客户端，决定超时与传输)

[OUTPUT]
- REQUIRED_CONTEXT_TOKENS: 本地模型被视为「长上下文」的最低 `num_ctx`
- probe_long_context_models: 并行读取 `/api/show` 的 `num_ctx`，返回达到阈值的模型名

[POS]
Ollama 上下文窗口探测。只读已安装模型的参数，不安装、不下载、不改配置。
"""

from __future__ import annotations

import asyncio

import httpx

REQUIRED_CONTEXT_TOKENS = 64000
# 只看前几个模型：一次健康检查不值得为几十个模型逐个发请求。
MAX_PROBES = 5
# 并行探测也要有总预算：Ollama 卡住时 doctor 不能被拖住十几秒。
PROBE_BUDGET_S = 3.0


async def probe_long_context_models(client: httpx.AsyncClient, base_url: str, models: list[str]) -> list[str]:
    """Return the models whose reported `num_ctx` is at or above the threshold.

    The probes run together under one budget: a hung daemon answers nothing, and the caller then
    reports the same warning it would for a model without a pinned context.
    """
    candidates = models[:MAX_PROBES]
    try:
        async with asyncio.timeout(PROBE_BUDGET_S):
            contexts = await asyncio.gather(*(_num_ctx_of(client, base_url, name) for name in candidates))
    except TimeoutError:
        return []
    return [name for name, ctx in zip(candidates, contexts, strict=True) if ctx >= REQUIRED_CONTEXT_TOKENS]


async def _num_ctx_of(client: httpx.AsyncClient, base_url: str, name: str) -> int:
    """The `num_ctx` a model reports through `/api/show`; 0 when it reports none."""
    try:
        response = await client.post(f"{base_url}/api/show", json={"model": name})
        if response.status_code != 200:
            return 0
        parameters = response.json().get("parameters")
    except (httpx.HTTPError, ValueError):
        return 0
    return _num_ctx(parameters) if isinstance(parameters, str) else 0


def _num_ctx(parameters: str) -> int:
    for line in parameters.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "num_ctx":
            try:
                return int(parts[1])
            except ValueError:
                return 0
    return 0
