"""Memory API router

Main router that aggregates all memory-related endpoints.
"""

import logging

from fastapi import APIRouter

from app.api.memory import (
    onboarding,
    sqlite_vec,
)
from app.api.memory.activity_compactor_router import (
    router as activity_compactor_router,
)
from app.api.memory.auto_memory_consolidation_router import (
    router as auto_memory_consolidation_router,
)
from app.api.memory.auto_recall_router import (
    router as auto_recall_router,
)
from app.api.memory.bitemporal_tms_router import (
    router as bitemporal_tms_router,
)
from app.api.memory.budget_packing_router import (
    router as budget_packing_router,
)
from app.api.memory.business_template_router import (
    router as business_template_router,
)
from app.api.memory.cjk_iteration_router import (
    router as cjk_iteration_router,
)
from app.api.memory.code_memory_compaction_router import (
    router as code_memory_compaction_router,
)
from app.api.memory.codebase_diff_router import (
    router as codebase_diff_router,
)
from app.api.memory.codegraph_router import router as codegraph_router
from app.api.memory.conclusion_attribution_router import (
    router as conclusion_attribution_router,
)
from app.api.memory.conversation_lineage_defense_router import (
    router as conversation_lineage_defense_router,
)
from app.api.memory.cross_agent_router import (
    router as cross_agent_router,
)
from app.api.memory.decay_lifecycle_router import (
    router as decay_lifecycle_router,
)
from app.api.memory.disk_reconciliation_router import (
    router as disk_reconciliation_router,
)
from app.api.memory.dream_cognitive_router import (
    router as dream_cognitive_router,
)
from app.api.memory.drift_router import (
    router as memory_drift_router,
)
from app.api.memory.ephemeral_delta_router import (
    router as ephemeral_delta_router,
)
from app.api.memory.experience_compounding_router import (
    router as experience_compounding_router,
)
from app.api.memory.experience_gene_router import (
    router as experience_gene_router,
)
from app.api.memory.experience_observability_router import (
    router as experience_observability_router,
)
from app.api.memory.follow_ups import router as follow_ups_router
from app.api.memory.four_layer_promotion_router import (
    router as four_layer_promotion_router,
)
from app.api.memory.four_tier_fts_router import (
    router as four_tier_fts_router,
)
from app.api.memory.git_okf_router import (
    router as git_okf_router,
)
from app.api.memory.graph_rrf_router import router as graph_rrf_router
from app.api.memory.hindsight_reflection_router import (
    router as hindsight_reflection_router,
)
from app.api.memory.hybrid_memory_router import (
    router as hybrid_memory_router,
)
from app.api.memory.inode_identity_router import (
    router as inode_identity_router,
)
from app.api.memory.job_compounding_router import (
    router as job_compounding_router,
)
from app.api.memory.kg_screening_router import (
    router as kg_screening_router,
)
from app.api.memory.live_correction_router import (
    router as live_correction_router,
)
from app.api.memory.markdown_chunker import (
    router as markdown_chunker_router,
)
from app.api.memory.markdown_curator_router import (
    router as markdown_curator_router,
)
from app.api.memory.mem_cube_router import (
    router as mem_cube_router,
)
from app.api.memory.memory_lineage_router import (
    router as memory_lineage_router,
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
from app.api.memory.noise_free_memory_router import (
    router as noise_free_memory_router,
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
from app.api.memory.peer_cognition_router import (
    router as peer_cognition_router,
)
from app.api.memory.pitfall_alert_router import (
    router as pitfall_alert_router,
)
from app.api.memory.private_notebook_router import (
    router as private_notebook_router,
)
from app.api.memory.profile_notes_router import router as profile_notes_router
from app.api.memory.quadruple_retrieval_router import (
    router as quadruple_retrieval_router,
)
from app.api.memory.relational_backtrack_router import (
    router as relational_backtrack_router,
)
from app.api.memory.revocable_provenance_router import (
    router as revocable_provenance_router,
)
from app.api.memory.rule_cascade_router import (
    router as rule_cascade_router,
)
from app.api.memory.score_honesty_router import (
    router as score_honesty_router,
)
from app.api.memory.screen_observation_safety_router import (
    router as screen_observation_safety_router,
)
from app.api.memory.skill_triad_router import (
    router as skill_triad_router,
)
from app.api.memory.space_guard import (
    router as space_guard_router,
)
from app.api.memory.task_triad_trajectory_router import (
    router as task_triad_trajectory_router,
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
router.include_router(auto_recall_router, tags=["memory-auto-recall"])
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
router.include_router(sqlite_vec.router, tags=["memory-sqlite-vec"])
router.include_router(
    screen_observation_safety_router,
    tags=["memory-screen-observation-safety"],
)
router.include_router(
    task_triad_trajectory_router,
    tags=["memory-triad-trajectory"],
)
router.include_router(
    activity_compactor_router,
    tags=["memory-activity-compactor"],
)
router.include_router(
    noise_free_memory_router,
    tags=["memory-noise-free-extractor"],
)
router.include_router(
    private_notebook_router,
    tags=["memory-private-notebook"],
)
router.include_router(
    job_compounding_router,
    tags=["memory-job-compounding"],
)
router.include_router(
    revocable_provenance_router,
    tags=["memory-revocable-provenance"],
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
    disk_reconciliation_router,
    tags=["memory-reconciliation"],
)
router.include_router(
    git_okf_router,
    tags=["memory-git-okf"],
)
router.include_router(
    hybrid_memory_router,
    tags=["memory-hybrid"],
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
    rule_cascade_router,
    tags=["memory-rule-cascade"],
)
router.include_router(
    relational_backtrack_router,
    tags=["memory-relational-backtrack"],
)
router.include_router(
    markdown_curator_router,
    tags=["memory-markdown-curator"],
)
router.include_router(
    business_template_router,
    tags=["memory-business-templates"],
)
router.include_router(
    experience_observability_router,
    tags=["memory-experience-observability"],
)
router.include_router(
    peer_cognition_router,
    tags=["memory-peer-cognition"],
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
    auto_memory_consolidation_router,
    tags=["memory-auto-consolidation"],
)
router.include_router(
    mem_cube_router,
    tags=["memory-cubes"],
)
router.include_router(
    dream_cognitive_router,
    tags=["memory-dream-cognitive"],
)
router.include_router(
    memory_lineage_router,
    tags=["memory-lineage"],
)
router.include_router(
    quadruple_retrieval_router,
    tags=["memory-quadruple-retrieval"],
)
router.include_router(
    live_correction_router,
    tags=["memory-live-correction-suite"],
)
router.include_router(
    space_guard_router,
    tags=["memory-space-guard"],
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
    pitfall_alert_router,
    tags=["memory-pitfall-alert"],
)
router.include_router(
    experience_compounding_router,
    tags=["memory-compounding"],
)
router.include_router(
    conclusion_attribution_router,
    tags=["memory-attribution"],
)
router.include_router(
    score_honesty_router,
    tags=["memory-score-honesty"],
)
router.include_router(
    codebase_diff_router,
    tags=["memory-codebase-diff"],
)
router.include_router(
    inode_identity_router,
    tags=["memory-inode-identity"],
)
router.include_router(
    cjk_iteration_router,
    tags=["memory-cjk-iteration"],
)
router.include_router(
    skill_triad_router,
    tags=["memory-skill-triad"],
)
router.include_router(
    bitemporal_tms_router,
    tags=["memory-bitemporal-tms"],
)
