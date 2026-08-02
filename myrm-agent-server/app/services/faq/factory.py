"""FAQ interceptor lazy singleton factory.

[POS] Creates and caches FaqInterceptor with process-level embedding+vector singletons.
"""

from __future__ import annotations

import logging

from app.services.faq.interceptor import FaqInterceptor

logger = logging.getLogger(__name__)

_interceptor: FaqInterceptor | None = None


async def get_faq_interceptor() -> FaqInterceptor | None:
    """Return the cached FaqInterceptor, or None if embedding/vector is unavailable."""
    global _interceptor
    if _interceptor is not None:
        return _interceptor

    try:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            get_embedding_config,
            get_embedding_service,
        )

        from app.core.retriever.vector.defaults import create_default_vector_store

        config = get_embedding_config()
        if not config.api_key:
            return None

        embedding_service = get_embedding_service(config)
        vector_store = await create_default_vector_store()
        if vector_store is None:
            return None

        _interceptor = FaqInterceptor(embedding_service, vector_store)
        return _interceptor
    except Exception:
        logger.debug("FAQ interceptor unavailable", exc_info=True)
        return None
