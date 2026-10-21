"""FastAPI router endpoints for the Lightweight P2P Agent Socket Mesh Protocol."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.socket_mesh import (
    AuditLogsResponseDTO,
    AwaitResponseDTO,
    CleanupStalePeersResponseDTO,
    EnvelopeDispatchResponseDTO,
    PeerInfoDTO,
    PeerListResponseDTO,
    PeerRegisterRequestDTO,
    PingResponseDTO,
    ReplyEnvelopeRequestDTO,
    SendEnvelopeRequestDTO,
)
from app.services.agent.socket_mesh_service import (
    SocketMeshService,
    get_socket_mesh_service,
)

router = APIRouter(prefix="/agents/socket-mesh", tags=["socket-mesh"])


@router.get(
    "/projects/{project}/peers",
    response_model=PeerListResponseDTO,
    summary="List all discovered peers in a project mesh",
)
def list_peers(
    project: str,
    auto_mark_stale: bool = Query(default=True, description="Whether to automatically mark inactive peers as stale"),
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> PeerListResponseDTO:
    peers = service.list_peers(project=project, auto_mark_stale=auto_mark_stale)
    return PeerListResponseDTO(project=project, total_peers=len(peers), peers=peers)


@router.post(
    "/projects/{project}/peers",
    response_model=PeerInfoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update an agent peer in the project mesh",
)
def register_peer(
    project: str,
    req: PeerRegisterRequestDTO,
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> PeerInfoDTO:
    return service.register_peer(project=project, req=req)


@router.get(
    "/projects/{project}/peers/{name}",
    response_model=PeerInfoDTO,
    summary="Get telemetry details for a single peer by name",
)
def get_peer(
    project: str,
    name: str,
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> PeerInfoDTO:
    peer = service.get_peer(project=project, name=name)
    if not peer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer '{name}' not found in project '{project}'",
        )
    return peer


@router.delete(
    "/projects/{project}/peers/{name}",
    response_model=Dict[str, object],
    summary="Unregister an agent peer and tear down its endpoint",
)
def unregister_peer(
    project: str,
    name: str,
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> Dict[str, object]:
    removed = service.unregister_peer(project=project, name=name)
    return {"success": removed, "name": name, "project": project}


@router.post(
    "/projects/{project}/messages/send",
    response_model=EnvelopeDispatchResponseDTO,
    summary="Asynchronously dispatch a prompt envelope to a peer",
)
async def send_message(
    project: str,
    req: SendEnvelopeRequestDTO,
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> EnvelopeDispatchResponseDTO:
    return await service.send_message(
        project=project,
        sender_name=req.sender_name,
        target_name=req.target_name,
        prompt=req.prompt,
        timeout_seconds=req.timeout_seconds,
    )


@router.post(
    "/projects/{project}/messages/reply",
    response_model=EnvelopeDispatchResponseDTO,
    summary="Reply to an inbound message from an agent peer",
)
async def reply_message(
    project: str,
    req: ReplyEnvelopeRequestDTO,
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> EnvelopeDispatchResponseDTO:
    return await service.reply_message(
        project=project,
        responder_name=req.responder_name,
        msg_id=req.msg_id,
        response_text=req.response_text,
        error=req.error,
    )


@router.get(
    "/projects/{project}/messages/{msg_id}/await",
    response_model=AwaitResponseDTO,
    summary="Wait for response envelope matching a message ID",
)
async def await_reply(
    project: str,
    msg_id: str,
    sender_name: str = Query(..., description="Name of the agent awaiting reply"),
    timeout_seconds: float = Query(default=30.0, description="Await timeout in seconds"),
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> AwaitResponseDTO:
    return await service.await_reply(
        project=project,
        sender_name=sender_name,
        msg_id=msg_id,
        timeout_seconds=timeout_seconds,
    )


@router.post(
    "/projects/{project}/peers/{target_name}/ping",
    response_model=PingResponseDTO,
    summary="Ping a peer and retrieve its telemetry AgentCard",
)
async def ping_peer(
    project: str,
    target_name: str,
    sender_name: str = Query(default="sentinel", description="Name of the agent sending the ping"),
    timeout_seconds: float = Query(default=5.0, description="Ping timeout in seconds"),
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> PingResponseDTO:
    return await service.ping_peer(
        project=project,
        sender_name=sender_name,
        target_name=target_name,
        timeout_seconds=timeout_seconds,
    )


@router.get(
    "/projects/{project}/audit-logs",
    response_model=AuditLogsResponseDTO,
    summary="Retrieve audit trail logs for the project mesh",
)
def get_audit_logs(
    project: str,
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> AuditLogsResponseDTO:
    logs = service.get_audit_logs(project=project)
    return AuditLogsResponseDTO(project=project, logs=logs)


@router.post(
    "/projects/{project}/cleanup",
    response_model=CleanupStalePeersResponseDTO,
    summary="Clean up stale/offline peers older than max_age_seconds",
)
def cleanup_stale_peers(
    project: str,
    max_age_seconds: float = Query(default=300.0, description="Maximum inactive age in seconds"),
    service: SocketMeshService = Depends(get_socket_mesh_service),
) -> CleanupStalePeersResponseDTO:
    cleaned = service.cleanup_stale_peers(project=project, max_age_seconds=max_age_seconds)
    return CleanupStalePeersResponseDTO(project=project, cleaned_count=cleaned)
