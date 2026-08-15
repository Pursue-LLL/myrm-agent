"""Local-only HTTP fixtures for Chrome MCP E2E tests.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: 部署模式判定，限制 seed 端点仅 local/tauri)
_inline_core (POS: citation / skill chip transcript / skill chip composer / embed seed)
_kanban (POS: Kanban closure / IN_REVIEW seed)
其余 seed 子模块（见 [test_fixtures/_ARCH.md](test_fixtures/_ARCH.md) 文件清单）

[OUTPUT]
router: 聚合门面，include 全部 seed 子模块 router（完整清单见 [test_fixtures/_ARCH.md](test_fixtures/_ARCH.md)）

[POS]
Chats API 本地测试 fixture 子包聚合入口。核心 seed 端点由 _inline_core 子模块提供，
Kanban seed 端点由 _kanban 子模块提供，其余 seed 端点由各业务子模块提供，全部仅 local/tauri 模式可用。
"""

from __future__ import annotations

from fastapi import APIRouter

from ._inline_core import router as inline_core_fixture_router
from ._kanban import router as kanban_fixture_router
from .allowed_tools_recovery import (
    router as allowed_tools_recovery_fixture_router,
)
from .chat_share import router as chat_share_fixture_router
from .clarify_refresh import router as clarify_refresh_fixture_router
from .context_retention import (
    router as context_retention_fixture_router,
)
from .copilot import router as copilot_fixture_router
from .deliverable import router as deliverable_fixture_router
from .evicted import router as evicted_fixture_router
from .file_edit_batch import router as file_edit_batch_fixture_router
from .file_mutation import router as file_mutation_fixture_router
from .guardrail_bash import router as guardrail_bash_fixture_router
from .memory_lifecycle import router as memory_lifecycle_fixture_router
from .prior_chat import router as prior_chat_fixture_router
from .revert import router as revert_fixture_router
from .rich_media_preview import (
    router as rich_media_preview_fixture_router,
)
from .security_preset import router as security_preset_fixture_router
from .stream_retry_busy import (
    router as stream_retry_busy_fixture_router,
)
from .tool_history_recovery import (
    router as tool_history_recovery_fixture_router,
)
from .wechat_draft import router as wechat_draft_fixture_router
from .wiki_dedup import router as wiki_dedup_fixture_router
from .wiki_provenance import router as wiki_provenance_fixture_router
from .workspace_merge import router as workspace_merge_fixture_router

router = APIRouter()

router.include_router(inline_core_fixture_router)
router.include_router(kanban_fixture_router)
router.include_router(deliverable_fixture_router)
router.include_router(copilot_fixture_router)
router.include_router(clarify_refresh_fixture_router)
router.include_router(chat_share_fixture_router)
router.include_router(file_edit_batch_fixture_router)
router.include_router(file_mutation_fixture_router)
router.include_router(workspace_merge_fixture_router)
router.include_router(evicted_fixture_router)
router.include_router(revert_fixture_router)
router.include_router(stream_retry_busy_fixture_router)
router.include_router(allowed_tools_recovery_fixture_router)
router.include_router(tool_history_recovery_fixture_router)
router.include_router(guardrail_bash_fixture_router)
router.include_router(wiki_dedup_fixture_router)
router.include_router(wiki_provenance_fixture_router)
router.include_router(context_retention_fixture_router)
router.include_router(rich_media_preview_fixture_router)
router.include_router(security_preset_fixture_router)
router.include_router(memory_lifecycle_fixture_router)
router.include_router(prior_chat_fixture_router)
router.include_router(wechat_draft_fixture_router)
