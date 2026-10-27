"""REST API router for Diamond Topology Orchestrator & Blinded Adversarial Auditor."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.diamond_graph import (
    AdversarialVerdictDTO,
    AuditDeliveryRequest,
    CensusStatusDTO,
    CreateDiamondPipelineRequest,
    DiamondNodeDTO,
    PruneEdgesResponseDTO,
    RecordNodeCompletionRequest,
    SynthesizeRequest,
)
from app.services.agent.diamond_graph_service import (
    DiamondGraphService,
    get_diamond_graph_service,
)

router = APIRouter(prefix="/chats/{chat_id}/diamond-graph", tags=["Diamond Graph & Blinded Auditor"])


@router.post("/pipeline", response_model=List[DiamondNodeDTO], status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    chat_id: str,
    req: CreateDiamondPipelineRequest,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> List[DiamondNodeDTO]:
    """Construct 3-stage Diamond Topology: N fan_out -> 1 reduce -> 1 synthesize."""
    return service.create_pipeline(chat_id, req.goal, req.fan_out_specs)


@router.post("/prune", response_model=PruneEdgesResponseDTO)
async def prune_false_dependencies(
    chat_id: str,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> PruneEdgesResponseDTO:
    """Strip artificial serialized dependencies between independent fan-out branches."""
    pruned, remaining = service.prune_false_dependencies(chat_id)
    return PruneEdgesResponseDTO(pruned_edges=pruned, remaining_nodes_count=remaining)


@router.post("/dispatch", response_model=CensusStatusDTO)
async def dispatch_fan_out(
    chat_id: str,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> CensusStatusDTO:
    """Dispatch all fan-out branches concurrently and return initial census."""
    return service.dispatch_fan_out(chat_id)


@router.post("/nodes/complete", response_model=DiamondNodeDTO)
async def record_node_completion(
    chat_id: str,
    req: RecordNodeCompletionRequest,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> DiamondNodeDTO:
    """Record completion outcome and store internal CoT reasoning strictly isolated from auditors."""
    try:
        return service.record_node_completion(
            chat_id=chat_id,
            node_id=req.node_id,
            output_artifact=req.output_artifact,
            cot_reasoning_internal=req.cot_reasoning_internal,
            success=req.success,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/census", response_model=CensusStatusDTO)
async def check_census(
    chat_id: str,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> CensusStatusDTO:
    """Dead-Node Census Sentinel: verify exact response count against dispatch."""
    return service.check_census(chat_id)


@router.post("/retry")
async def retry_dead_nodes(
    chat_id: str,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> dict[str, List[str]]:
    """Pinpoint missing or failed fan-out nodes and trigger immediate retry."""
    retried = service.retry_dead_nodes(chat_id)
    return {"retried_nodes": retried}


@router.post("/reduce")
async def execute_deterministic_reduce(
    chat_id: str,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> dict[str, str]:
    """Execute deterministic 0-token deduplication and aggregation across fan-out nodes."""
    try:
        reduced = service.execute_deterministic_reduce(chat_id)
        return {"reduced_artifact": reduced}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/synthesize")
async def execute_synthesis(
    chat_id: str,
    req: SynthesizeRequest,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> dict[str, str]:
    """Execute top tier synthesis upon reduced findings."""
    try:
        synth = service.execute_synthesis(chat_id, summary_prefix=req.summary_prefix)
        return {"synthesized_artifact": synth}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/nodes", response_model=List[DiamondNodeDTO])
async def get_nodes(
    chat_id: str,
    mask_cot: bool = Query(True, description="Strictly strip internal CoT to preserve audit isolation"),
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> List[DiamondNodeDTO]:
    """List all nodes in the diamond DAG with optional CoT isolation."""
    return service.get_nodes(chat_id, mask_cot=mask_cot)


@router.post("/audit", response_model=AdversarialVerdictDTO)
async def audit_delivery(
    chat_id: str,
    req: AuditDeliveryRequest,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> AdversarialVerdictDTO:
    """Evaluate delivery through 3-perspective blinded adversarial audit and immutable reality anchors."""
    return service.audit_delivery(
        chat_id=chat_id,
        artifact=req.artifact,
        reality_anchors=req.reality_anchors,
        pass_vote_ratio=req.pass_vote_ratio,
    )


@router.post("/reset")
async def reset_session(
    chat_id: str,
    service: DiamondGraphService = Depends(get_diamond_graph_service),
) -> dict[str, bool]:
    """Reset diamond orchestrator and auditor session state."""
    service.reset_session(chat_id)
    return {"reset": True}
