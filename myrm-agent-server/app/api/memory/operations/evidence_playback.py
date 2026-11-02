"""Memory evidence playback endpoint.

[INPUT]
app.services.memory.evidence.playback_service::EvidencePlaybackService (POS: 证据溯源会话切片服务)

[OUTPUT]
router: `GET /memory/command-center/evidence/playback` sanitized conversation slice behind a memory's evidence badge.

[POS]
记忆证据溯源 API 操作层。对所有用户挂载：记忆卡片的证据徽标点开后由溯源抽屉调用。
路径前缀为 `/command-center`；与 `command_center.py` 不同，它不受 `MYRM_MEMORY_LABS` 开关控制。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.schemas.memory.command_center import MemoryEvidencePlaybackResponse
from app.services.memory.evidence.playback_service import EvidencePlaybackService

router = APIRouter(prefix="/command-center")


@router.get("/evidence/playback", response_model=MemoryEvidencePlaybackResponse)
async def get_evidence_playback(
    source_id: str | None = None,
    message_id: str | None = None,
    channel_id: str | None = None,
    quote_snippet: str | None = None,
    author_id: str | None = None,
    author_name: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> MemoryEvidencePlaybackResponse:
    """Return sanitized conversation slice or graceful snapshot for evidence verification."""
    service = EvidencePlaybackService(db)
    return await service.get_playback(
        source_id=source_id,
        message_id=message_id,
        channel_id=channel_id,
        quote_snippet=quote_snippet,
        author_id=author_id,
        author_name=author_name,
    )
