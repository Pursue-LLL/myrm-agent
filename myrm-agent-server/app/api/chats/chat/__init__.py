"""聊天API接口"""

from fastapi import APIRouter

from ..test_fixtures import router as test_fixtures_router
from .catchup import router as catchup_router
from .compaction import router as compaction_router
from .core import router as core_router
from .fork import router as fork_router
from .handoff import router as handoff_router
from .messages import router as messages_router
from .sandbox import router as sandbox_router
from .share import router as share_router
from .title import router as title_router
from .trash import router as trash_router
from .turn import router as turn_router

router = APIRouter()

router.include_router(test_fixtures_router)
router.include_router(trash_router)
router.include_router(catchup_router)
router.include_router(messages_router)
router.include_router(core_router)
router.include_router(title_router)
router.include_router(turn_router)
router.include_router(compaction_router)
router.include_router(fork_router)
router.include_router(handoff_router)
router.include_router(sandbox_router)
router.include_router(share_router)
