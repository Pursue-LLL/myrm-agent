"""Wiki Knowledge Base API router.

[INPUT]
fastapi::APIRouter (POS: FastAPI 路由容器)
app.api.wiki.routes.ingest_stream::register_ingest_stream_routes (POS: SSE/流式 ingest 路由注册)
app.api.wiki.routes::query, dedup, stats, tree, mutations, queue, insights, imports, vault, portability,
    url_import, video_import, meeting (POS: Wiki 各业务域子路由)
app.api.wiki.routes.governance, layers_routes, maintain_routes, obsidian_binding_routes (POS: 既有独立子路由)
app.api.wiki.routes.sources (POS: 来源管理子路由)
app.api.wiki.routes.clip, routes.ima (POS: 剪藏与图像理解子路由)

[OUTPUT]
router: 挂在 /wiki 下的聚合路由器。

[POS]
Wiki API 的组合根。只负责按原路径顺序挂载子路由，业务实现位于 routes/ 与各独立 *_routes.py。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import (
    dedup,
    imports,
    insights,
    meeting,
    mutations,
    portability,
    query,
    queue,
    stats,
    tree,
    url_import,
    vault,
    video_import,
)
from app.api.wiki.routes.ingest_stream import register_ingest_stream_routes
from app.api.wiki.routes.schemas import ConceptBacklinkItem, ConceptLinkItem, ConceptLinksResponse

router = APIRouter()

# 对测试与调用方保持的公开门面：依赖覆盖需要用同一个函数对象。
__all__ = [
    "ConceptBacklinkItem",
    "ConceptLinkItem",
    "ConceptLinksResponse",
    "_get_wiki_archiver",
    "router",
]

router.include_router(query.router)
router.include_router(dedup.router)
router.include_router(stats.router)
router.include_router(tree.router)
router.include_router(mutations.router)
router.include_router(queue.router)
router.include_router(insights.router)
router.include_router(imports.router)
router.include_router(vault.router)
router.include_router(portability.router)
router.include_router(url_import.router)
router.include_router(video_import.router)
router.include_router(meeting.router)

register_ingest_stream_routes(router)

from app.api.wiki.routes.clip import router as wiki_clip_router  # noqa: E402
from app.api.wiki.routes.governance import router as wiki_governance_router  # noqa: E402
from app.api.wiki.routes.ima import router as wiki_ima_router  # noqa: E402
from app.api.wiki.routes.layers import router as wiki_layers_router  # noqa: E402
from app.api.wiki.routes.maintain import router as wiki_maintain_router  # noqa: E402
from app.api.wiki.routes.obsidian_binding import router as wiki_obsidian_binding_router  # noqa: E402
from app.api.wiki.routes.sources import router as wiki_sources_router  # noqa: E402

router.include_router(wiki_clip_router)
router.include_router(wiki_maintain_router)
router.include_router(wiki_sources_router)
router.include_router(wiki_ima_router)
router.include_router(wiki_obsidian_binding_router)
router.include_router(wiki_governance_router)
router.include_router(wiki_layers_router)
