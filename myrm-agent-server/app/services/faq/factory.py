"""FAQ interceptor lazy singleton factory.

[INPUT]
- app.services.agent.platform_config::load_platform_retrieval_configs (POS: WebUI retrieval config SSOT)
- myrm_agent_harness.toolkits.retriever.embedding.factory::get_embedding_service (POS: embedding service factory)

[OUTPUT]
- get_faq_interceptor: cached FaqInterceptor bound to the WebUI embedding config, or None
- reset_faq_interceptor: drop the cached instance after retrieval config changes

[POS]
FAQ 拦截器装配入口。Embedding 配置一律来自 WebUI 设置（DB），与 Memory / Curator / Cron
等服务走同一条 `load_platform_retrieval_configs` 通道；未配置时返回 None，调用方按“无 FAQ
拦截”继续正常 Agent 执行。进程级单例，配置变更后由 reset_faq_interceptor 重置。
"""

from __future__ import annotations

import logging

from app.services.faq.interceptor import FaqInterceptor

logger = logging.getLogger(__name__)

_interceptor: FaqInterceptor | None = None


async def get_faq_interceptor() -> FaqInterceptor | None:
    """Return the cached FaqInterceptor, or None when embedding/vector is unavailable."""
    global _interceptor
    if _interceptor is not None:
        return _interceptor

    try:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            get_embedding_service,
        )

        from app.core.retriever.vector.defaults import create_default_vector_store
        from app.services.agent.platform_config import load_platform_retrieval_configs

        embedding_config, _ = await load_platform_retrieval_configs()
        if embedding_config is None:
            return None

        embedding_service = get_embedding_service(embedding_config)
        vector_store = await create_default_vector_store()

        _interceptor = FaqInterceptor(embedding_service, vector_store)
        return _interceptor
    except Exception:
        logger.debug("FAQ interceptor unavailable", exc_info=True)
        return None


def reset_faq_interceptor() -> None:
    """Drop the cached interceptor so the next call rebuilds it from current config."""
    global _interceptor
    _interceptor = None


__all__ = [
    "get_faq_interceptor",
    "reset_faq_interceptor",
]
