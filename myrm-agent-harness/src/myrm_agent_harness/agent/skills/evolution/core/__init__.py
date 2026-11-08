"""Public surface of the skill evolution core package.

[INPUT]
- agent.skills.evolution.core.types::EvolutionLayer, EvolutionProposal, EvolutionRequest,
  EvolutionType, FailurePathology, SkillLineage, SkillRecord, SkillVerificationType, VerificationProof
  (POS: 技能演化数据契约层)

[OUTPUT]
- The evolution proposal/lineage type contracts

[POS]
Public surface of the skill evolution core. Import from here rather than from the internal
modules so the module layout can evolve without breaking callers.
"""

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionLayer,
    EvolutionProposal,
    EvolutionRequest,
    EvolutionType,
    FailurePathology,
    SkillLineage,
    SkillRecord,
    SkillVerificationType,
    VerificationProof,
)

__all__ = [
    "EvolutionLayer",
    "EvolutionProposal",
    "EvolutionRequest",
    "EvolutionType",
    "FailurePathology",
    "SkillLineage",
    "SkillRecord",
    "SkillVerificationType",
    "VerificationProof",
]
