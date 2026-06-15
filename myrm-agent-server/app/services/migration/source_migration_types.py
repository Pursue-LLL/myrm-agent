"""External source migration lane types.

[INPUT]
Loaded external source payloads from source_payload_loader.

[OUTPUT]
SourceInstructionPlan, MigrationWizardOptions, lane preview DTOs.

[POS]
Typed contracts for the four-lane migration orchestrator (instruction / memory / skill / credential).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkspaceRuleWrite:
    """A workspace rule file to create under .myrm/rules/."""

    filename: str
    content: str


@dataclass
class SourceInstructionPlan:
    """Instruction-layer content extracted from a external assistant install."""

    competitor: str
    agent_persona: str = ""
    global_supplement: str = ""
    workspace_rules: list[WorkspaceRuleWrite] = field(default_factory=list)
    mcp_servers: dict[str, object] | None = None


@dataclass(frozen=True)
class MigrationWizardOptions:
    """User-selected migration binding (persisted on dry-run session metadata)."""

    target_agent_id: str | None = None
    clone_from_agent_id: str = "builtin-general"
    include_episodic: bool = False
    apply_global_instructions: bool = True


@dataclass(frozen=True)
class InstructionApplyResult:
    """Outcome of writing instruction-lane content."""

    target_agent_id: str
    agent_created: bool
    global_instructions_updated: bool
    workspace_rules_written: int
    workspace_rules_skipped: int = 0
    profile_snapshot_id: str | None = None
    previous_global_instructions: str = ""
    written_rule_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstructionRollbackRecord:
    """Persisted instruction-lane rollback facts (stored on import batch metadata)."""

    target_agent_id: str
    profile_snapshot_id: str | None
    previous_global_instructions: str
    global_instructions_updated: bool
    written_rule_paths: tuple[str, ...]
    competitor: str
    agent_created: bool = False


@dataclass(frozen=True)
class MigrationLanePreview:
    """Content-safe preview row for the migration wizard."""

    lane: str
    status: str
    label: str
    detail: str


INSTRUCTION_CHAR_WARN_THRESHOLD = 8000


def instruction_char_total(instruction: SourceInstructionPlan) -> int:
    """Total instruction-lane character count (persona + global supplement + rules)."""

    total = len(instruction.agent_persona.strip()) + len(instruction.global_supplement.strip())
    for rule in instruction.workspace_rules:
        total += len(rule.content.strip())
    return total


def build_lane_previews(
    *,
    instruction: SourceInstructionPlan,
    memory_mapped: int,
    memory_status: str,
    skill_count: int,
    has_api_keys: bool,
    providers_ready: bool,
    include_episodic: bool,
) -> list[MigrationLanePreview]:
    """Build four-lane preview rows for the GUI."""

    persona_len = len(instruction.agent_persona.strip())
    global_len = len(instruction.global_supplement.strip())
    rules_count = len(instruction.workspace_rules)
    char_total = instruction_char_total(instruction)

    instruction_detail_parts: list[str] = []
    if persona_len:
        instruction_detail_parts.append(f"agent persona ({persona_len} chars)")
    if global_len:
        instruction_detail_parts.append(f"global supplement ({global_len} chars)")
    if rules_count:
        instruction_detail_parts.append(f"{rules_count} workspace rule file(s)")
    instruction_detail = ", ".join(instruction_detail_parts) if instruction_detail_parts else "none detected"
    if char_total > INSTRUCTION_CHAR_WARN_THRESHOLD:
        instruction_detail += f"; {char_total} chars total (large — may increase token cost)"

    instruction_status = "missing"
    if instruction_detail != "none detected":
        instruction_status = "warning" if char_total > INSTRUCTION_CHAR_WARN_THRESHOLD else "ready"

    memory_detail = f"{memory_mapped} mapped item(s)"
    if not include_episodic:
        memory_detail += ", episodic excluded"

    credential_status = "missing"
    credential_detail = "no keys in .env"
    if has_api_keys:
        if providers_ready:
            credential_status = "manual"
            credential_detail = "API keys available (opt-in import)"
        else:
            credential_status = "critical"
            credential_detail = "API keys in .env but no model providers configured — set up providers first"

    return [
        MigrationLanePreview(
            lane="instruction",
            status=instruction_status,
            label="instruction_lane",
            detail=instruction_detail,
        ),
        MigrationLanePreview(
            lane="memory",
            status=memory_status if memory_mapped else "missing",
            label="memory_lane",
            detail=memory_detail,
        ),
        MigrationLanePreview(
            lane="skill",
            status="review" if skill_count else "missing",
            label="skill_lane",
            detail=f"{skill_count} skill(s) pending review" if skill_count else "no skills",
        ),
        MigrationLanePreview(
            lane="credential",
            status=credential_status,
            label="credential_lane",
            detail=credential_detail,
        ),
    ]
