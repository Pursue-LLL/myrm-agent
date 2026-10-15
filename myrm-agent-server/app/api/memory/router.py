"""Memory API router

Main router that aggregates all memory-related endpoints.
"""

import logging

from fastapi import APIRouter

from app.api.memory import onboarding
from app.api.memory.budget_packing_router import (
    router as budget_packing_router,
)
from app.api.memory.code_memory_compaction_router import (
    router as code_memory_compaction_router,
)
from app.api.memory.codegraph_router import router as codegraph_router
from app.api.memory.conversation_lineage_defense_router import (
    router as conversation_lineage_defense_router,
)
from app.api.memory.cross_agent_router import (
    router as cross_agent_router,
)
from app.api.memory.decay_lifecycle_router import (
    router as decay_lifecycle_router,
)
from app.api.memory.drift_router import (
    router as memory_drift_router,
)
from app.api.memory.ephemeral_delta_router import (
    router as ephemeral_delta_router,
)
from app.api.memory.experience_gene_router import (
    router as experience_gene_router,
)
from app.api.memory.follow_ups import router as follow_ups_router
from app.api.memory.four_layer_promotion_router import (
    router as four_layer_promotion_router,
)
from app.api.memory.four_tier_fts_router import (
    router as four_tier_fts_router,
)
from app.api.memory.graph_rrf_router import router as graph_rrf_router
from app.api.memory.hindsight_reflection_router import (
    router as hindsight_reflection_router,
)
from app.api.memory.kg_screening_router import (
    router as kg_screening_router,
)
from app.api.memory.markdown_chunker import (
    router as markdown_chunker_router,
)
from app.api.memory.mem_cube_router import (
    router as mem_cube_router,
)
from app.api.memory.migration_readiness_seed import (
    router as migration_readiness_fixture_router,
)
from app.api.memory.migration_router import (
    router as memory_migration_router,
)
from app.api.memory.migration_wizard import (
    router as migration_wizard_router,
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
    shared_contexts,
)
from app.api.memory.private_notebook_router import (
    router as private_notebook_router,
)
from app.api.memory.profile_notes_router import router as profile_notes_router
from app.api.memory.score_honesty_router import (
    router as score_honesty_router,
)
from app.api.memory.temporal_graph_router import (
    router as temporal_graph_router,
)
from app.api.memory.test_seed import router as memory_test_seed_router
from app.api.memory.two_layer_dialectic_router import (
    router as two_layer_dialectic_router,
)
from app.config.deploy_mode import is_local_mode
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

if settings.memory_labs_enabled:
    router.include_router(command_center.router, tags=["memory-command-center"])
    router.include_router(command_center_consolidation.router, tags=["memory-command-center"])
    router.include_router(command_center_diagnostics.router, tags=["memory-command-center"])

router.include_router(pending.router, tags=["memory-pending"])
router.include_router(conflicts.router, tags=["memory-conflicts"])
router.include_router(shared_context_health.router, tags=["memory-shared-contexts"])
router.include_router(shared_contexts.router, tags=["memory-shared-contexts"])
router.include_router(shared_context_history.router, tags=["memory-shared-contexts"])
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
router.include_router(memory_drift_router, tags=["memory-drift-defense"])
router.include_router(memory_migration_router, tags=["memory-sovereign-migration"])
router.include_router(cross_agent_router, tags=["memory-cross-agent"])
router.include_router(kg_screening_router, tags=["memory-kg-screening"])

router.include_router(radar.router, tags=["memory-radar"])
router.include_router(follow_ups_router, tags=["memory-follow-ups"])
if is_local_mode():
    router.include_router(migration_readiness_fixture_router, tags=["memory-test-fixtures"])
    router.include_router(memory_test_seed_router, tags=["memory-test-fixtures"])
router.include_router(onboarding.router, tags=["memory-onboarding-insight"])
router.include_router(
    private_notebook_router,
    tags=["memory-private-notebook"],
)
router.include_router(
    four_tier_fts_router,
    tags=["memory-four-tier-fts"],
)
router.include_router(
    temporal_graph_router,
    tags=["memory-temporal-graph"],
)
router.include_router(
    conversation_lineage_defense_router,
    tags=["memory-lineage-defense"],
)
router.include_router(
    ephemeral_delta_router,
    tags=["memory-ephemeral-delta"],
)
router.include_router(
    two_layer_dialectic_router,
    tags=["memory-two-layer-dialectic"],
)
router.include_router(
    budget_packing_router,
    tags=["memory-budget-packing"],
)
router.include_router(
    mem_cube_router,
    tags=["memory-cubes"],
)
router.include_router(
    markdown_chunker_router,
    tags=["memory-chunker"],
)
router.include_router(
    migration_wizard_router,
    tags=["memory-migration-wizard"],
)
router.include_router(
    score_honesty_router,
    tags=["memory-score-honesty"],
)
