"""Visual Modular Agent Assembler API Router.

[INPUT]
- AssemblyBlueprintDTO, AssemblyDryRunRequestDTO

[OUTPUT]
- AssemblyValidationResponseDTO, SandboxDryRunResponseDTO, list[CapabilityBlockDTO]

[POS]
app/api/agents/agent_assembler_router.py: REST endpoints for block-based capability composition,
dependency checking, and instant sandbox dry-run testing.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services.agent.agent_assembler_service import (
    AgentAssemblerService,
    AssemblyBlueprint,
    CapabilityBlock,
    CapabilityBlockCategory,
    agent_assembler_service,
)

router = APIRouter(prefix="/agents/assembler", tags=["Agent Assembler"])


class CapabilityBlockDTO(BaseModel):
    id: str
    category: CapabilityBlockCategory
    name: str
    description: str
    enabled: bool = True
    config: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)


class AssemblyBlueprintDTO(BaseModel):
    name: str = ""
    description: str = ""
    blocks: list[CapabilityBlockDTO] = Field(default_factory=list)


class AssemblyValidationResponseDTO(BaseModel):
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    suggestions: list[str]
    estimated_token_cost: int


class AssemblyDryRunRequestDTO(BaseModel):
    blueprint: AssemblyBlueprintDTO
    prompt: str = Field(..., min_length=1)


class SandboxDryRunResponseDTO(BaseModel):
    simulated_response: str
    resolved_system_prompt: str
    predicted_tool_calls: list[str]
    latency_ms: int
    tokens_used: int


def _dto_to_domain(dto: AssemblyBlueprintDTO) -> AssemblyBlueprint:
    domain_blocks = [
        CapabilityBlock(
            id=b.id,
            category=b.category,
            name=b.name,
            description=b.description,
            enabled=b.enabled,
            config=b.config,
        )
        for b in dto.blocks
    ]
    return AssemblyBlueprint(
        name=dto.name,
        description=dto.description,
        blocks=domain_blocks,
    )


@router.post("/validate", response_model=AssemblyValidationResponseDTO, status_code=status.HTTP_200_OK)
async def validate_assembly(
    payload: AssemblyBlueprintDTO,
) -> AssemblyValidationResponseDTO:
    """Validate block dependencies, missing essentials, and security constraints."""
    domain_bp = _dto_to_domain(payload)
    result = agent_assembler_service.validate_assembly(domain_bp)
    return AssemblyValidationResponseDTO(
        is_valid=result.is_valid,
        errors=result.errors,
        warnings=result.warnings,
        suggestions=result.suggestions,
        estimated_token_cost=result.estimated_token_cost,
    )


@router.post("/dry-run", response_model=SandboxDryRunResponseDTO, status_code=status.HTTP_200_OK)
async def dry_run_assembly(
    payload: AssemblyDryRunRequestDTO,
) -> SandboxDryRunResponseDTO:
    """Execute single-step testbed dry-run against the assembled blocks."""
    domain_bp = _dto_to_domain(payload.blueprint)
    result = agent_assembler_service.dry_run_assembly(domain_bp, payload.prompt)
    return SandboxDryRunResponseDTO(
        simulated_response=result.simulated_response,
        resolved_system_prompt=result.resolved_system_prompt,
        predicted_tool_calls=result.predicted_tool_calls,
        latency_ms=result.latency_ms,
        tokens_used=result.tokens_used,
    )


@router.get("/block-catalog", response_model=list[CapabilityBlockDTO], status_code=status.HTTP_200_OK)
async def get_block_catalog() -> list[CapabilityBlockDTO]:
    """Retrieve all pre-configured capability block cards across the 6 dimensions."""
    raw_catalog = agent_assembler_service.get_block_catalog()
    return [
        CapabilityBlockDTO(
            id=b.id,
            category=b.category,
            name=b.name,
            description=b.description,
            enabled=b.enabled,
            config=b.config,
        )
        for b in raw_catalog
    ]
