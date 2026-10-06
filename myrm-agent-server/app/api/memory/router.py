"""Memory API router

Main router that aggregates all memory-related endpoints.
"""

import logging

from fastapi import APIRouter

from app.api.memory import dream_diary
from app.api.memory.auto_recall_router import (
    router as auto_recall_router,
)
from app.api.memory.code_memory_compaction_router import (
    router as code_memory_compaction_router,
)
from app.api.memory.codegraph_router import router as codegraph_router
from app.api.memory.conflict_router import (
    router as memory_conflict_router,
)
from app.api.memory.decay_lifecycle_router import (
    router as decay_lifecycle_router,
)
from app.api.memory.drift_router import (
    router as memory_drift_router,
)
from app.api.memory.dual_track_router import (
    router as memory_dual_track_router,
)
from app.api.memory.experience_gene_router import (
    router as experience_gene_router,
)
from app.api.memory.follow_ups import router as follow_ups_router
from app.api.memory.four_layer_promotion_router import (
    router as four_layer_promotion_router,
)
from app.api.memory.graph_rrf_router import router as graph_rrf_router
from app.api.memory.hindsight_reflection_router import (
    router as hindsight_reflection_router,
)
from app.api.memory.mcp_router import (
    router as memory_mcp_router,
)
from app.api.memory.migration_readiness_seed import (
    router as migration_readiness_fixture_router,
)
from app.api.memory.migration_router import (
    router as memory_migration_router,
)
from app.api.memory.openclaw_router import (
    router as memory_openclaw_router,
)
from app.api.memory.operations import (
    archive_restore,
    backup,
    backup_remote,
    command_center,
    command_center_consolidation,
    command_center_diagnostics,
    conflicts,
    crud,
    domain_mesh,
    external_transcripts,
    guardian,
    head_probe,
    pending,
    radar,
    reindex,
    tool_guidance,
    working_state,
)
from app.api.memory.operations.shared_context import (
    shared_context_health,
    shared_context_history,
    shared_context_migration,
    shared_contexts,
)
from app.api.memory.privacy_router import (
    router as memory_privacy_router,
)
from app.api.memory.profile_notes_router import router as profile_notes_router
from app.api.memory.self_verification_router import (
    router as memory_self_verification_router,
)
from app.api.memory.test_seed import router as memory_test_seed_router
from app.api.memory.universal_mcp_router import (
    router as memory_universal_mcp_router,
)
from app.api.memory.unload_router import (
    router as memory_unload_router,
)
from app.api.memory.vector_preflight_router import (
    router as memory_vector_preflight_router,
)
from app.api.memory.wiki_memory_router import (
    router as wiki_memory_router,
)
from app.api.memory.zero_llm_memory_router import (
    router as zero_llm_memory_router,
)

logger = logging.getLogger(__name__)

router = APIRouter()

router.include_router(command_center.router, tags=["memory-command-center"])
router.include_router(command_center_consolidation.router, tags=["memory-command-center"])
router.include_router(command_center_diagnostics.router, tags=["memory-command-center"])
router.include_router(pending.router, tags=["memory-pending"])
router.include_router(conflicts.router, tags=["memory-conflicts"])
router.include_router(shared_context_health.router, tags=["memory-shared-contexts"])
router.include_router(shared_contexts.router, tags=["memory-shared-contexts"])
router.include_router(shared_context_history.router, tags=["memory-shared-contexts"])
router.include_router(shared_context_migration.router, tags=["memory-shared-contexts"])
router.include_router(guardian.router, tags=["memory-guardian"])
router.include_router(working_state.router, tags=["memory-working-state"])
router.include_router(crud.router, tags=["memory-crud"])
router.include_router(head_probe.router, tags=["memory-head"])
router.include_router(backup.router, tags=["memory-backup"])
router.include_router(backup_remote.router, tags=["memory-backup-remote"])
router.include_router(reindex.router, tags=["memory-reindex"])
router.include_router(archive_restore.router, tags=["memory-archive-restore"])
router.include_router(tool_guidance.router, tags=["memory-tool-guidance"])
router.include_router(external_transcripts.router, tags=["memory-external-transcripts"])
router.include_router(domain_mesh.router, tags=["memory-domain-mesh"])
router.include_router(profile_notes_router, tags=["memory-profile-notes"])
router.include_router(four_layer_promotion_router, tags=["memory-four-layer-promotion"])
router.include_router(codegraph_router, tags=["memory-codegraph"])
router.include_router(decay_lifecycle_router, tags=["memory-decay-lifecycle"])
router.include_router(graph_rrf_router, tags=["memory-graph-rrf"])
router.include_router(hindsight_reflection_router, tags=["memory-hindsight-reflection"])
router.include_router(code_memory_compaction_router, tags=["memory-code-compaction"])
router.include_router(experience_gene_router, tags=["memory-experience-genes"])
router.include_router(auto_recall_router, tags=["memory-auto-recall"])
router.include_router(wiki_memory_router, tags=["memory-wiki"])
router.include_router(zero_llm_memory_router, tags=["memory-zero-llm"])
router.include_router(memory_privacy_router, tags=["memory-privacy"])
router.include_router(memory_mcp_router, tags=["memory-mcp-interop"])
router.include_router(memory_drift_router, tags=["memory-drift-defense"])
router.include_router(memory_unload_router, tags=["memory-unload-guard"])
router.include_router(memory_migration_router, tags=["memory-sovereign-migration"])
router.include_router(memory_conflict_router, tags=["memory-conflict-arbitration"])
router.include_router(memory_openclaw_router, tags=["memory-openclaw-adapter"])
router.include_router(memory_dual_track_router, tags=["memory-dual-track"])
router.include_router(memory_universal_mcp_router, tags=["memory-universal-mcp"])
router.include_router(memory_vector_preflight_router, tags=["memory-vector-preflight"])
router.include_router(memory_self_verification_router, tags=["memory-self-verification"])

router.include_router(radar.router, tags=["memory-radar"])
router.include_router(follow_ups_router, tags=["memory-follow-ups"])
router.include_router(migration_readiness_fixture_router, tags=["memory-test-fixtures"])
router.include_router(memory_test_seed_router, tags=["memory-test-fixtures"])
router.include_router(dream_diary.router, tags=["memory-dream-diary"])
router.include_router(dream_diary.unlearn_router, tags=["memory-surgical-unlearn"])
