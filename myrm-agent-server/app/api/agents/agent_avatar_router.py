"""Agent Avatar Generation & Dice Lock API Router.

[INPUT]
- GenerateSvgAvatarRequestDTO, GenerateAiAvatarRequestDTO, SetAgentAvatarRequestDTO

[OUTPUT]
- SvgAvatarResponseDTO, AiAvatarResponseDTO, AvatarMetadataDTO

[POS]
app/api/agents/agent_avatar_router.py: REST endpoints for deterministic SVG dice roll avatars,
AI prompt avatar dispatch, and profile avatar locking.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.services.agent.agent_avatar_service import (
    AvatarMetadata,
    AvatarStyle,
    agent_avatar_service,
)

router = APIRouter(prefix="/agents/avatar", tags=["Agent Avatar"])


class GenerateSvgAvatarRequestDTO(BaseModel):
    seed: str = Field(..., min_length=1, description="Deterministic seed for SVG generation")
    style: AvatarStyle = Field(default=AvatarStyle.BEAM, description="Visual style preset")
    background_color: str = Field(default="#6366f1", description="Hex background color (e.g. #4f46e5)")


class SvgAvatarResponseDTO(BaseModel):
    seed: str
    style: AvatarStyle
    background_color: str
    svg_data: str


class GenerateAiAvatarRequestDTO(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt describing the avatar persona")
    style: str = Field(default="photorealistic", description="Artistic visual style")


class AiAvatarResponseDTO(BaseModel):
    prompt: str
    image_url: str


class SetAgentAvatarRequestDTO(BaseModel):
    seed: str
    style: AvatarStyle
    background_color: str
    is_locked: bool = True
    svg_data: str
    image_url: str | None = None


class AvatarMetadataDTO(BaseModel):
    seed: str
    style: AvatarStyle
    background_color: str
    is_locked: bool
    svg_data: str
    image_url: str | None = None
    created_at_epoch: int


@router.post("/generate-svg", response_model=SvgAvatarResponseDTO, status_code=status.HTTP_200_OK)
async def generate_svg_avatar(
    payload: GenerateSvgAvatarRequestDTO,
) -> SvgAvatarResponseDTO:
    """Generate pure deterministic SVG avatar based on seed string and style."""
    svg_data = agent_avatar_service.generate_deterministic_svg(
        seed=payload.seed,
        style=payload.style,
        bg_color=payload.background_color,
    )
    return SvgAvatarResponseDTO(
        seed=payload.seed,
        style=payload.style,
        background_color=payload.background_color,
        svg_data=svg_data,
    )


@router.post("/generate-ai", response_model=AiAvatarResponseDTO, status_code=status.HTTP_200_OK)
async def generate_ai_avatar(
    payload: GenerateAiAvatarRequestDTO,
) -> AiAvatarResponseDTO:
    """Generate or retrieve AI persona avatar image based on prompt."""
    image_url = agent_avatar_service.generate_ai_avatar(
        prompt=payload.prompt,
        style=payload.style,
    )
    return AiAvatarResponseDTO(
        prompt=payload.prompt,
        image_url=image_url,
    )


@router.post("/{agent_id}", response_model=AvatarMetadataDTO, status_code=status.HTTP_200_OK)
async def set_agent_avatar(
    agent_id: str,
    payload: SetAgentAvatarRequestDTO,
) -> AvatarMetadataDTO:
    """Set and lock chosen avatar for specific agent."""
    metadata = AvatarMetadata(
        seed=payload.seed,
        style=payload.style,
        background_color=payload.background_color,
        is_locked=payload.is_locked,
        svg_data=payload.svg_data,
        image_url=payload.image_url,
    )
    saved = agent_avatar_service.set_agent_avatar(agent_id, metadata)
    return AvatarMetadataDTO(
        seed=saved.seed,
        style=saved.style,
        background_color=saved.background_color,
        is_locked=saved.is_locked,
        svg_data=saved.svg_data,
        image_url=saved.image_url,
        created_at_epoch=saved.created_at_epoch,
    )


@router.get("/{agent_id}", response_model=AvatarMetadataDTO, status_code=status.HTTP_200_OK)
async def get_agent_avatar(
    agent_id: str,
) -> AvatarMetadataDTO:
    """Retrieve saved avatar metadata for agent."""
    existing = agent_avatar_service.get_agent_avatar(agent_id)
    if existing is None:
        # Generate on-demand default unlocked avatar for the agent
        default_svg = agent_avatar_service.generate_deterministic_svg(agent_id, AvatarStyle.BEAM)
        existing = AvatarMetadata(
            seed=agent_id,
            style=AvatarStyle.BEAM,
            background_color="#6366f1",
            is_locked=False,
            svg_data=default_svg,
        )
        agent_avatar_service.set_agent_avatar(agent_id, existing)

    return AvatarMetadataDTO(
        seed=existing.seed,
        style=existing.style,
        background_color=existing.background_color,
        is_locked=existing.is_locked,
        svg_data=existing.svg_data,
        image_url=existing.image_url,
        created_at_epoch=existing.created_at_epoch,
    )
