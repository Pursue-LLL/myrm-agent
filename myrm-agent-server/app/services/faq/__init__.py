"""
[POS] Channel FAQ 语义缓存服务包。提供 FAQ 语料 CRUD、语义拦截、命中追踪。
"""

from .corpus import FaqCorpusService
from .interceptor import FaqInterceptor, FaqMatchResult
from .tracker import FaqHitTracker

__all__ = [
    "FaqCorpusService",
    "FaqInterceptor",
    "FaqMatchResult",
    "FaqHitTracker",
]
