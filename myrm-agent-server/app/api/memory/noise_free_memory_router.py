"""API endpoints for Tool-Noise-Free Memory Extraction and Purge Generation Epoch Suite.

[INPUT]
- FastAPI: APIRouter, Depends, Query
- Schemas: app.schemas.noise_free_memory
- Service: app.services.memory.noise_free_memory_service

[OUTPUT]
- noise_free_memory_router: Router mounted under /api/memory/noise-free

[POS]
Topic 01 Item 88 API layer (Anthropic Commerce Agents-style memory isolation, PII regex screening, and monotonic epoch fencing).
"""

from fastapi import APIRouter, Depends, Query

from app.schemas.noise_free_memory import (
    CleanDialogueRequestDTO,
    CleanDialogueResponseDTO,
    CommitFactRequestDTO,
    CommitFactResponseDTO,
    EpochStatusResponseDTO,
    ExtractedFactCandidateDTO,
    InspectPIIRequestDTO,
    InspectPIIResponseDTO,
    PurgeMemoryRequestDTO,
    PurgeMemoryResponseDTO,
)
from app.services.memory.noise_free_memory_service import (
    NoiseFreeMemoryService,
    get_noise_free_memory_service,
)

router = APIRouter(prefix="/noise-free", tags=["Memory Noise-Free Extraction & Purge Epoch"])


@router.post("/clean-dialogue", response_model=CleanDialogueResponseDTO)
async def clean_dialogue(
    request: CleanDialogueRequestDTO,
    service: NoiseFreeMemoryService = Depends(get_noise_free_memory_service),
) -> CleanDialogueResponseDTO:
    """Strip external tool outputs and XML tags to prepare noise-free extraction context."""
    return service.prepare_clean_dialogue(request)


@router.post("/inspect-pii", response_model=InspectPIIResponseDTO)
async def inspect_pii(
    request: InspectPIIRequestDTO,
    service: NoiseFreeMemoryService = Depends(get_noise_free_memory_service),
) -> InspectPIIResponseDTO:
    """Inspect candidate memory statement against code-level PII regular expression gateway."""
    return service.inspect_pii_statement(request)


@router.post("/commit-fact", response_model=CommitFactResponseDTO)
async def commit_fact(
    request: CommitFactRequestDTO,
    service: NoiseFreeMemoryService = Depends(get_noise_free_memory_service),
) -> CommitFactResponseDTO:
    """Validate candidate fact against monotonic generation epoch fence and PII rules before saving."""
    return service.commit_extracted_fact(request)


@router.post("/purge", response_model=PurgeMemoryResponseDTO)
async def purge_memory(
    request: PurgeMemoryRequestDTO,
    service: NoiseFreeMemoryService = Depends(get_noise_free_memory_service),
) -> PurgeMemoryResponseDTO:
    """Atomically clear memory facts and bump generation epoch to prevent stale async resurrection."""
    return service.purge_user_memory(request)


@router.get("/status", response_model=EpochStatusResponseDTO)
async def get_status(
    user_id: str = Query(default="default_user", description="User identifier"),
    service: NoiseFreeMemoryService = Depends(get_noise_free_memory_service),
) -> EpochStatusResponseDTO:
    """Get current generation epoch health, stale drops, and blocked PII violations."""
    return service.get_epoch_status(user_id)


@router.get("/facts", response_model=list[ExtractedFactCandidateDTO])
async def get_facts(
    user_id: str = Query(default="default_user", description="User identifier"),
    service: NoiseFreeMemoryService = Depends(get_noise_free_memory_service),
) -> list[ExtractedFactCandidateDTO]:
    """Retrieve all committed clean memory facts for user."""
    return service.get_user_facts(user_id)
