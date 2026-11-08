"""FAQ interceptor factory: one interceptor per embedding configuration.

[INPUT]
- app.services.agent.platform_config::load_platform_retrieval_configs (POS: WebUI retrieval config SSOT)
- myrm_agent_harness.toolkits.retriever.embedding.factory::get_embedding_service (POS: embedding service factory)

[OUTPUT]
- get_faq_interceptor: the FaqInterceptor bound to the embedding config saved right now, or None

[POS]
FAQ 拦截器装配入口。Embedding 配置一律来自 WebUI 设置（DB），与 Memory / Curator / Cron
等服务走同一条 `load_platform_retrieval_configs` 通道（该通道自带短 TTL 缓存，保存配置时立即失效）；
未配置时返回 None，调用方按“无 FAQ 拦截”继续正常 Agent 执行。拦截器按 embedding 配置（模型 / 密钥 / 地址，
与 harness 的 embedding 服务缓存同一个键）缓存：每次调用都比对当前配置，配置一变就用新配置重建，
所以无论经由哪条保存路径（单项 PUT 或 UI 使用的批量同步）改了配置，都不需要任何重置钩子。
"""

from __future__ import annotations

import logging

from app.services.faq.interceptor import FaqInterceptor

logger = logging.getLogger(__name__)

# (model, api_key, api_base): what identifies the embedding service the interceptor embeds with.
_EmbeddingKey = tuple[str, str | None, str | None]

# Kept while the config is unchanged, not rebuilt per call: create_default_vector_store() hands a remote
# Qdrant deployment a new client every time, so a per-call interceptor would open one connection per message.
_cached: tuple[_EmbeddingKey, FaqInterceptor] | None = None


async def get_faq_interceptor() -> FaqInterceptor | None:
    """Return the interceptor for the embedding config saved right now, or None when embedding/vector is unavailable."""
    global _cached
    try:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            get_embedding_service,
        )

        from app.core.retriever.vector.defaults import create_default_vector_store
        from app.services.agent.platform_config import load_platform_retrieval_configs

        embedding_config, _ = await load_platform_retrieval_configs()
        if embedding_config is None:
            _cached = None
            return None

        key = (embedding_config.model, embedding_config.api_key, embedding_config.api_base)
        if _cached is not None and _cached[0] == key:
            return _cached[1]

        interceptor = FaqInterceptor(get_embedding_service(embedding_config), await create_default_vector_store())
        _cached = (key, interceptor)
        return interceptor
    except Exception:
        logger.debug("FAQ interceptor unavailable", exc_info=True)
        return None


__all__ = ["get_faq_interceptor"]
