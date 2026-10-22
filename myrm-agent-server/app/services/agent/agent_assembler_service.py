"""Modular Agent Assembler & Block-Based Capability Composer Service.

[INPUT]
- AssemblyBlueprint, CapabilityBlock, DryRunRequest

[OUTPUT]
- AssemblyValidationResult, SandboxDryRunResult, list[CapabilityBlock]

[POS]
app/services/agent/agent_assembler_service.py: Core business logic for validating
and dry-running visual modular agent assemblies.
"""

import time
from dataclasses import dataclass, field
from enum import Enum


class CapabilityBlockCategory(str, Enum):
    BRAIN = "brain"
    PERSONA = "persona"
    TOOLS = "tools"
    SKILLS = "skills"
    MEMORY = "memory"
    SANDBOX = "sandbox"


@dataclass(frozen=True)
class CapabilityBlock:
    id: str
    category: CapabilityBlockCategory
    name: str
    description: str
    enabled: bool = True
    config: dict[str, str | int | float | bool | list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class AssemblyBlueprint:
    name: str
    description: str = ""
    blocks: list[CapabilityBlock] = field(default_factory=list)


@dataclass(frozen=True)
class AssemblyValidationResult:
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    suggestions: list[str]
    estimated_token_cost: int


@dataclass(frozen=True)
class SandboxDryRunResult:
    simulated_response: str
    resolved_system_prompt: str
    predicted_tool_calls: list[str]
    latency_ms: int
    tokens_used: int


class AgentAssemblerService:
    """Service providing dependency validation and dry-run simulation for agent blueprints."""

    def validate_assembly(self, blueprint: AssemblyBlueprint) -> AssemblyValidationResult:
        """Validate block dependencies, security rules, and structural soundness."""
        errors: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []

        active_blocks = [b for b in blueprint.blocks if b.enabled]
        categories_present = {b.category for b in active_blocks}

        # 1. Brain validation: At least one brain module is mandatory
        if CapabilityBlockCategory.BRAIN not in categories_present:
            errors.append("Missing Brain block: At least one LLM router/model block must be selected.")
        else:
            brain_blocks = [b for b in active_blocks if b.category == CapabilityBlockCategory.BRAIN]
            primary_model = brain_blocks[0].config.get("primary_model", "")
            if not primary_model:
                warnings.append("Brain block has no primary model specified; falling back to system default.")

        # 2. Persona validation
        if CapabilityBlockCategory.PERSONA not in categories_present:
            warnings.append("No Persona block attached: Agent will operate using neutral system defaults.")
            suggestions.append("Add a Persona block with clear guidelines to improve task focus.")

        # 3. Tools & Sandbox dependency matching
        tool_blocks = [b for b in active_blocks if b.category == CapabilityBlockCategory.TOOLS]
        has_python_microtools = any(bool(b.config.get("has_python_microtool", False)) for b in tool_blocks)
        sandbox_blocks = [b for b in active_blocks if b.category == CapabilityBlockCategory.SANDBOX]

        if has_python_microtools and not sandbox_blocks:
            warnings.append("Python microtools enabled without an explicit Sandbox isolation block.")
            suggestions.append("Attach a Sandbox block to constrain process timeout and file writes.")

        # 4. Memory policy validation
        memory_blocks = [b for b in active_blocks if b.category == CapabilityBlockCategory.MEMORY]
        if len(memory_blocks) > 1:
            warnings.append("Multiple Memory blocks detected; first active policy will take precedence.")

        # 5. Estimate token baseline
        estimated_tokens = 250  # Base system scaffold
        for b in active_blocks:
            if b.category == CapabilityBlockCategory.PERSONA:
                prompt_text = str(b.config.get("prompt_template", ""))
                estimated_tokens += max(len(prompt_text.split()) * 2, 80)
            elif b.category == CapabilityBlockCategory.TOOLS:
                tool_list = b.config.get("tool_names", [])
                if isinstance(tool_list, list):
                    estimated_tokens += len(tool_list) * 45
            elif b.category == CapabilityBlockCategory.SKILLS:
                estimated_tokens += 120
            elif b.category == CapabilityBlockCategory.MEMORY:
                estimated_tokens += 100

        is_valid = len(errors) == 0
        return AssemblyValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
            estimated_token_cost=estimated_tokens,
        )

    def dry_run_assembly(self, blueprint: AssemblyBlueprint, prompt: str) -> SandboxDryRunResult:
        """Simulate single-turn execution against assembled blocks in sandbox testbed."""
        start_time = time.perf_counter()
        validation = self.validate_assembly(blueprint)

        if not validation.is_valid:
            return SandboxDryRunResult(
                simulated_response=f"Dry-run aborted due to validation failure: {'; '.join(validation.errors)}",
                resolved_system_prompt="[Invalid Configuration]",
                predicted_tool_calls=[],
                latency_ms=1,
                tokens_used=0,
            )

        active_blocks = [b for b in blueprint.blocks if b.enabled]

        # Resolve system prompt
        persona_blocks = [b for b in active_blocks if b.category == CapabilityBlockCategory.PERSONA]
        if persona_blocks:
            base_prompt = str(persona_blocks[0].config.get("prompt_template", "You are an autonomous AI Agent."))
            signature = str(persona_blocks[0].config.get("persona_signature", ""))
            if signature:
                base_prompt = f"{base_prompt}\nSignature: {signature}"
        else:
            base_prompt = "You are an autonomous AI Agent executing requested instructions."

        # Predict tool activation
        predicted_tools: list[str] = []
        lower_prompt = prompt.lower()
        tool_blocks = [b for b in active_blocks if b.category == CapabilityBlockCategory.TOOLS]
        for tb in tool_blocks:
            raw_tools = tb.config.get("tool_names", [])
            if isinstance(raw_tools, list):
                for t_name in raw_tools:
                    t_str = str(t_name).lower()
                    if any(kw in lower_prompt for kw in ["run", "exec", "calc", "search", "file", "test"]):
                        if t_str not in predicted_tools:
                            predicted_tools.append(str(t_name))

        elapsed_ms = int((time.perf_counter() - start_time) * 1000) + 12

        # Formulate simulated output
        simulated_text = (
            f'Simulated execution for: "{prompt}"\n'
            f"- Model Pipeline: {blueprint.name or 'Default'}\n"
            f"- Predicted Tools Invoked: {', '.join(predicted_tools) if predicted_tools else 'None (Direct Text)'}\n"
            f"- System Baseline: {validation.estimated_token_cost} tokens"
        )

        return SandboxDryRunResult(
            simulated_response=simulated_text,
            resolved_system_prompt=base_prompt,
            predicted_tool_calls=predicted_tools,
            latency_ms=elapsed_ms,
            tokens_used=validation.estimated_token_cost + len(prompt.split()) + 40,
        )

    def get_block_catalog(self) -> list[CapabilityBlock]:
        """Return predefined building blocks across all six dimensions."""
        return [
            CapabilityBlock(
                id="brain-sonnet",
                category=CapabilityBlockCategory.BRAIN,
                name="Claude 3.7 Sonnet (Hybrid Reasoning)",
                description="High-reasoning brain model with dynamic thinking budget control.",
                config={"primary_model": "claude-3-7-sonnet", "temperature": 0.2, "fallback_model": "gpt-4o-mini"},
            ),
            CapabilityBlock(
                id="brain-gpt4o",
                category=CapabilityBlockCategory.BRAIN,
                name="GPT-4o Omnipresent",
                description="Balanced intelligence and high-throughput execution brain.",
                config={"primary_model": "gpt-4o", "temperature": 0.3},
            ),
            CapabilityBlock(
                id="persona-engineer",
                category=CapabilityBlockCategory.PERSONA,
                name="Principal Full-Stack Engineer",
                description="Clean architecture, zero any types, test-driven craftsmanship.",
                config={
                    "prompt_template": "You are a World-Class Software Architect. Deliver production-grade, tested code.",
                    "persona_signature": "Engineering Excellence First",
                },
            ),
            CapabilityBlock(
                id="persona-analyst",
                category=CapabilityBlockCategory.PERSONA,
                name="Data & Research Analyst",
                description="Evidence-based reasoning, citation verification and data synthesis.",
                config={
                    "prompt_template": "You are a Senior Quantitative Analyst. Always verify citations and compute precisely.",
                    "persona_signature": "Evidence & Grounded Truth",
                },
            ),
            CapabilityBlock(
                id="tools-core-dev",
                category=CapabilityBlockCategory.TOOLS,
                name="Core Development Toolset",
                description="File read/write, bash execution, AST analysis tools.",
                config={
                    "tool_names": ["read_file", "write_to_file", "run_command", "replace_file_content"],
                    "has_python_microtool": True,
                },
            ),
            CapabilityBlock(
                id="skills-github-ci",
                category=CapabilityBlockCategory.SKILLS,
                name="GitHub Actions & CI Mastery",
                description="Pre-compiled domain skill for CI/CD workflow crafting.",
                config={"skill_slug": "github-actions-ci", "version": "1.2.0"},
            ),
            CapabilityBlock(
                id="memory-hierarchical",
                category=CapabilityBlockCategory.MEMORY,
                name="Hierarchical Vector & Graph Memory",
                description="Multi-tier semantic retrieval and episodic recall.",
                config={"enable_semantic": True, "enable_episodic": True, "isolation_scope": "project"},
            ),
            CapabilityBlock(
                id="sandbox-strict",
                category=CapabilityBlockCategory.SANDBOX,
                name="Restricted Sandbox Container",
                description="Read-only root, safe directory writes, 30s timeout cap.",
                config={"timeout_seconds": 30, "allow_net": True, "write_scoped": True},
            ),
        ]


agent_assembler_service = AgentAssemblerService()
