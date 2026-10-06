"""API route for conversation anchor scroll search with exact phrase highlights.

[INPUT]
fastapi::APIRouter, Query (POS: FastAPI 路由组件)
app.services.chat.conversation_anchor_search_service::ConversationAnchorSearchService (POS: 锚点定位与高亮切片服务)
app.schemas.anchor_search::ConversationAnchorSearchResponseData (POS: 响应数据模型)
app.schemas.responses::StandardSuccessResponse (POS: 统一成功响应结构)

[OUTPUT]
router: APIRouter instance exposing GET /anchor-search.

[POS]
会话精确定位与高亮搜索路由层。暴露 GET /anchor-search 端点，为客户端提供基于精确短语、布尔组合与滑动窗口高亮的定位锚点。
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.schemas.anchor_search import (
    ConversationAnchorSearchHit,
    ConversationAnchorSearchResponseData,
)
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.conversation_anchor_search_service import (
    ConversationAnchorSearchService,
)

router = APIRouter()


@router.get("/anchor-search", response_model=StandardSuccessResponse)
async def search_conversation_anchors(
    q: str = Query(..., min_length=1, max_length=200, description="Exact phrase or keyword query"),
    chat_id: str | None = Query(None, description="Optional target conversation ID to restrict search"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    window_chars: int = Query(100, ge=20, le=500, description="Surrounding context window slice size"),
) -> JSONResponse:
    """Search messages with exact phrase highlight and anchor scroll targeting metadata.

    Returns exact matched phrases, bounded prefix/suffix context slices, and character offsets
    to allow smooth client-side scrolling and glow animations directly to the target anchor.
    """
    try:
        hits: list[ConversationAnchorSearchHit] = await ConversationAnchorSearchService.search_anchors(
            q,
            chat_id=chat_id,
            limit=limit,
            window_chars=window_chars,
        )
        data = ConversationAnchorSearchResponseData(items=hits, total=len(hits))
        return success_response(data=data.model_dump())
    except Exception as e:
        raise internal_error(operation="Search conversation anchors", exception=e) from e
