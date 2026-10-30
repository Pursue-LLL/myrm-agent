"""Skill Evolution System - Framework Layer.

Provides out-of-the-box skill self-evolution capabilities for myrm-agent-harness.

Core features:
- FIX evolution: auto-repair a skill a failed run was attributed to
- DERIVED evolution: rewrite a skill from user feedback
- Two-phase screener: cooldown, then an LLM check that the failure is a skill defect
- Rejection tracking: the screener's verdicts and the reasons a user gave when rejecting a proposal
"""

from .core.engine import SkillEvolutionEngine
from .core.gene_bank import GeneBankArchive
from .core.proposal_builder import ProposalBuilder
from .core.skill_on_disk import skill_from_disk
from .core.types import (
    EvolutionLayer,
    EvolutionProposal,
    EvolutionRequest,
    EvolutionType,
    FailurePathology,
    GeneCellKey,
    GeneEliteRecord,
    SkillLineage,
    SkillRecord,
    SkillVerificationType,
    VerificationProof,
)
from .db.store import SkillStore
from .execution.dependency import SkillDependencyTracker, get_dependency_tracker
from .execution.evaluator import BatchEvaluator
from .infra.integration import EvolutionIntegration, enable_skill_evolution, get_global_evolution_integration
from .infra.queue import EvolutionQueue, QueuePriority, get_evolution_queue
from .pipeline.patch import PatchType, SkillPatchResult, apply_skill_patch, detect_patch_type, parse_multi_file_full
from .pipeline.screener import EvolutionScreener, ScreeningResult
from .pipeline.trace_analyzer import TraceAnalyzer
from .pipeline.variant_generator import VariantGenerator

__all__ = [
    "BatchEvaluator",
    # Caching
    # Integration ( One-line enablement)
    "EvolutionIntegration",
    "EvolutionProposal",
    # Queue
    "EvolutionQueue",
    "EvolutionRequest",
    # Two-phase screener (P0)
    "EvolutionScreener",
    # Types
    "EvolutionLayer",
    "EvolutionType",
    "FailurePathology",
    "GeneBankArchive",
    "GeneCellKey",
    "GeneEliteRecord",
    "SkillVerificationType",
    "VerificationProof",
    # Patch system
    "PatchType",
    "ProposalBuilder",
    "QueuePriority",
    "ScreeningResult",
    # Dependencies
    "SkillDependencyTracker",
    # Core components
    "SkillEvolutionEngine",
    "SkillLineage",
    "SkillPatchResult",
    "SkillRecord",
    "SkillStore",
    "TraceAnalyzer",
    "VariantGenerator",
    # Utils
    "apply_skill_patch",
    "detect_patch_type",
    "enable_skill_evolution",
    "get_dependency_tracker",
    "get_evolution_queue",
    "get_global_evolution_integration",
    "parse_multi_file_full",
    "skill_from_disk",
]
