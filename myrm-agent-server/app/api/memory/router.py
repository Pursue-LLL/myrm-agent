"""Memory API router

Main router that aggregates all memory-related endpoints.
"""

import logging

from fastapi import APIRouter

from app.api.memory import (
    batch_learn,
    capacity_hitl,
    cognitive_box,
    context_ingestion,
    cvfs,
    decisions,
    decontamination,
    dream_diary,
    external_bridge,
    ltra,
    migration,
    onboarding,
    proactive_care,
    repair,
    sqlite_vec,
    tombstone,
    tool_backup,
    world_model,
    zero_hallucination,
)
from app.api.memory.activity_compactor_router import (
    router as activity_compactor_router,
)
from app.api.memory.authoritative_conclusions_router import (
    router as authoritative_conclusions_router,
)
from app.api.memory.auto_recall_router import (
    router as auto_recall_router,
)
from app.api.memory.budget_curator import (
    router as memory_budget_curator_router,
)
from app.api.memory.business_template_router import (
    router as business_template_router,
)
from app.api.memory.client_partition import (
    router as memory_client_partition_router,
)
from app.api.memory.code_memory_compaction_router import (
    router as code_memory_compaction_router,
)
from app.api.memory.codegraph_router import router as codegraph_router
from app.api.memory.conflict_router import (
    router as memory_conflict_router,
)
from app.api.memory.conversation_lineage_defense_router import (
    router as conversation_lineage_defense_router,
)
from app.api.memory.cross_agent_router import (
    router as cross_agent_router,
)
from app.api.memory.crystallization_router import (
    router as memory_crystallization_router,
)
from app.api.memory.decay_lifecycle_router import (
    router as decay_lifecycle_router,
)
from app.api.memory.dialectic import (
    router as memory_dialectic_router,
)
from app.api.memory.dialectic_guard_router import (
    router as dialectic_guard_router,
)
from app.api.memory.disk_reconciliation_router import (
    router as disk_reconciliation_router,
)
from app.api.memory.drift_router import (
    router as memory_drift_router,
)
from app.api.memory.dual_track_router import (
    router as memory_dual_track_router,
)
from app.api.memory.ephemeral_delta_router import (
    router as ephemeral_delta_router,
)
from app.api.memory.experience_gene_router import (
    router as experience_gene_router,
)
from app.api.memory.experience_injection_router import (
    router as experience_injection_router,
)
from app.api.memory.experience_observability_router import (
    router as experience_observability_router,
)
from app.api.memory.fact_supersession_router import (
    router as fact_supersession_router,
)
from app.api.memory.failure_search_router import (
    router as failure_search_router,
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
from app.api.memory.intent_reflection_router import (
    router as memory_intent_reflection_router,
)
from app.api.memory.job_compounding_router import (
    router as job_compounding_router,
)
from app.api.memory.kg_screening_router import (
    router as kg_screening_router,
)
from app.api.memory.lineage_search_router import (
    router as lineage_search_router,
)
from app.api.memory.markdown_curator_router import (
    router as markdown_curator_router,
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
from app.api.memory.noise_free_memory_router import (
    router as noise_free_memory_router,
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
from app.api.memory.override_stack_router import (
    router as memory_override_stack_router,
)
from app.api.memory.peer_cognition_router import (
    router as peer_cognition_router,
)
from app.api.memory.peer_gateway_router import (
    router as peer_gateway_router,
)
from app.api.memory.persona_router import (
    router as memory_persona_router,
)
from app.api.memory.privacy_router import (
    router as memory_privacy_router,
)
from app.api.memory.private_notebook_router import (
    router as private_notebook_router,
)
from app.api.memory.procedure_experience_router import (
    router as procedure_experience_router,
)
from app.api.memory.profile_notes_router import router as profile_notes_router
from app.api.memory.progressive_sidecar_router import (
    router as progressive_sidecar_router,
)
from app.api.memory.provenance_batch import (
    router as memory_provenance_batch_router,
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
from app.api.memory.screen_observation_safety_router import (
    router as screen_observation_safety_router,
)
from app.api.memory.self_verification_router import (
    router as memory_self_verification_router,
)
from app.api.memory.session_commit_router import (
    router as session_commit_router,
)
from app.api.memory.shared_bus import (
    router as memory_shared_bus_router,
)
from app.api.memory.subagent_isolation import (
    router as memory_subagent_isolation_router,
)
from app.api.memory.task_triad_trajectory_router import (
    router as task_triad_trajectory_router,
)
from app.api.memory.temporal_graph_router import (
    router as temporal_graph_router,
)
from app.api.memory.test_seed import router as memory_test_seed_router
from app.api.memory.thinking_sanitizer_router import (
    router as thinking_sanitizer_router,
)
from app.api.memory.tiered_consensus_router import (
    router as tiered_consensus_router,
)
from app.api.memory.two_layer_dialectic_router import (
    router as two_layer_dialectic_router,
)
from app.api.memory.universal_mcp_router import (
    router as memory_universal_mcp_router,
)
from app.api.memory.unload_router import (
    router as memory_unload_router,
)
from app.api.memory.vector_preflight_router import (
    router as memory_vector_preflight_router,
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
router.include_router(memory_crystallization_router, tags=["memory-crystallization"])
router.include_router(memory_intent_reflection_router, tags=["memory-intent-reflection"])
router.include_router(memory_override_stack_router, tags=["memory-override-stack"])
router.include_router(memory_persona_router, tags=["memory-persona-router"])
router.include_router(memory_client_partition_router, tags=["memory-client-partition"])
router.include_router(memory_provenance_batch_router, tags=["memory-provenance-batch"])
router.include_router(memory_shared_bus_router, tags=["memory-shared-bus"])
router.include_router(memory_budget_curator_router, tags=["memory-budget-curator"])
router.include_router(memory_dialectic_router, tags=["memory-dialectic"])
router.include_router(memory_subagent_isolation_router, tags=["memory-subagent-isolation"])
router.include_router(cross_agent_router, tags=["memory-cross-agent"])
router.include_router(kg_screening_router, tags=["memory-kg-screening"])

router.include_router(radar.router, tags=["memory-radar"])
router.include_router(follow_ups_router, tags=["memory-follow-ups"])
router.include_router(migration_readiness_fixture_router, tags=["memory-test-fixtures"])
router.include_router(memory_test_seed_router, tags=["memory-test-fixtures"])
router.include_router(dream_diary.router, tags=["memory-dream-diary"])
router.include_router(dream_diary.unlearn_router, tags=["memory-surgical-unlearn"])
router.include_router(ltra.router, tags=["memory-ltra-cognitive"])
router.include_router(onboarding.router, tags=["memory-onboarding-insight"])
router.include_router(external_bridge.router, tags=["memory-external-skill-bridge"])
router.include_router(zero_hallucination.router, tags=["memory-zero-hallucination-diagnostics"])
router.include_router(world_model.router, tags=["memory-world-model"])
router.include_router(sqlite_vec.router, tags=["memory-sqlite-vec"])
router.include_router(decisions.router, tags=["memory-engineering-decisions"])
router.include_router(repair.router, tags=["memory-repair"])
router.include_router(tool_backup.router, tags=["memory-tool-backup"])
router.include_router(context_ingestion.router, tags=["memory-context-ingestion"])
router.include_router(decontamination.router, tags=["memory-decontamination"])
router.include_router(cvfs.router, tags=["memory-cvfs"])
router.include_router(cognitive_box.router, tags=["memory-cognitive-box"])
router.include_router(proactive_care.router, tags=["memory-proactive-care"])
router.include_router(capacity_hitl.router, tags=["memory-capacity-hitl"])
router.include_router(migration.router, tags=["memory-migration"])
router.include_router(batch_learn.router, tags=["memory-batch-learn"])
router.include_router(tombstone.router, tags=["memory-tombstone"])
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
    lineage_search_router,
    tags=["memory-lineage-search"],
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
    fact_supersession_router,
    tags=["memory-fact-supersession"],
)
router.include_router(
    procedure_experience_router,
    tags=["memory-procedure-experience"],
)
router.include_router(
    experience_injection_router,
    tags=["memory-experience-injection"],
)
router.include_router(
    session_commit_router,
    tags=["memory-session-commit"],
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
    failure_search_router,
    tags=["memory-failure-search"],
)
router.include_router(
    peer_cognition_router,
    tags=["memory-peer-cognition"],
)
router.include_router(
    authoritative_conclusions_router,
    tags=["memory-conclusions"],
)
router.include_router(
    two_layer_dialectic_router,
    tags=["memory-two-layer-dialectic"],
)
router.include_router(
    peer_gateway_router,
    tags=["memory-peer-gateway"],
)
router.include_router(
    tiered_consensus_router,
    tags=["memory-tiered-consensus"],
)
router.include_router(
    thinking_sanitizer_router,
    tags=["memory-thinking-sanitizer"],
)
router.include_router(
    dialectic_guard_router,
    tags=["memory-dialectic-guard"],
)
router.include_router(
    progressive_sidecar_router,
    tags=["memory-progressive-sidecar"],
)






