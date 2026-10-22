"""[INPUT]
- chat_id: Path parameter for the target chat session
- Handshake query params: client_epoch, client_version, client_timestamp_ms
- ZeroReplaySnapshotService: Business layer service

[OUTPUT]
- GET /{chat_id}/atomic-snapshot: Returns single atomic snapshot payload
- GET /{chat_id}/live-stream: Zero-event-replay live SSE stream with handshake validation
- POST /{chat_id}/snapshot-state: Internal update of session state snapshot
- POST /{chat_id}/live-event: Broadcasts a live-only event with incremented state version

[POS]
API route layer for Atomic Snapshot and Live Stream Zero-Replay Reconnect Protocol (Item 36 P0).
Follows earendil-works/pi harness-v2 UI model specification.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.zero_replay import ZeroReplaySnapshotService

router = APIRouter()


class UpdateSnapshotStateRequest(BaseModel):
    status: Literal["idle", "running", "paused", "interrupted", "error"] | None = None
    leaf_entry_id: str | None = None
    active_tool_calls: list[dict[str, str]] | None = None
    message_count: int | None = None
    latest_turn_summary: str | None = None
    artifacts_summary: list[dict[str, str]] | None = None
    metadata: dict[str, str] | None = None


class BroadcastLiveEventRequest(BaseModel):
    event_type: str = Field(..., description="Event type name")
    payload: dict[str, str] = Field(default_factory=dict, description="Event data payload")


@router.get("/{chat_id}/atomic-snapshot", response_model=StandardSuccessResponse)
async def get_atomic_snapshot(chat_id: str) -> JSONResponse:
    """Returns a single atomic state snapshot for the requested chat session."""
    service = ZeroReplaySnapshotService.get_instance()
    snapshot = service.get_atomic_snapshot(chat_id)
    serialized = service.serialize_snapshot(snapshot)
    return success_response(serialized)


@router.post("/{chat_id}/snapshot-state", response_model=StandardSuccessResponse)
async def update_snapshot_state(
    chat_id: str,
    body: UpdateSnapshotStateRequest,
) -> JSONResponse:
    """Updates atomic state components and returns the updated snapshot."""
    service = ZeroReplaySnapshotService.get_instance()
    snapshot = service.update_session_state(
        session_id=chat_id,
        status=body.status,
        leaf_entry_id=body.leaf_entry_id,
        active_tool_calls=body.active_tool_calls,
        message_count=body.message_count,
        latest_turn_summary=body.latest_turn_summary,
        artifacts_summary=body.artifacts_summary,
        metadata=body.metadata,
    )
    return success_response(service.serialize_snapshot(snapshot))


@router.post("/{chat_id}/live-event", response_model=StandardSuccessResponse)
async def broadcast_live_event(
    chat_id: str,
    body: BroadcastLiveEventRequest,
) -> JSONResponse:
    """Dispatches a live event stamped with an incremental version and timestamp."""
    service = ZeroReplaySnapshotService.get_instance()
    event_payload = service.create_live_event_payload(
        session_id=chat_id,
        event_type=body.event_type,
        payload=dict(body.payload),
    )
    return success_response(event_payload)


@router.get("/{chat_id}/live-stream")
async def subscribe_live_stream(
    chat_id: str,
    request: Request,
    client_epoch: str = Query(..., description="Client epoch id from last snapshot"),
    client_version: int = Query(..., description="Client state version from last snapshot"),
    client_timestamp_ms: float = Query(..., description="Client snapshot timestamp in ms"),
) -> StreamingResponse:
    """Zero-Replay live SSE stream.

    Handshakes with client:
    - If client epoch/version is stale or invalid, immediately emits `handshake_failed` with full reload directive.
    - Otherwise, establishes live subscription and streams ONLY events generated strictly after client_version.
    """
    service = ZeroReplaySnapshotService.get_instance()
    handshake_result = service.evaluate_handshake(
        session_id=chat_id,
        client_epoch_id=client_epoch,
        client_version=client_version,
    )

    filter_config = service.create_live_filter_config(
        client_snapshot_timestamp_ms=client_timestamp_ms,
        client_state_version=client_version,
        allow_equal_timestamp=False,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        if handshake_result == "require_full_snapshot_reload":
            err_data = json.dumps(
                {
                    "error": "handshake_failed",
                    "action": "require_full_snapshot_reload",
                    "reason": "Client epoch or version drift detected",
                }
            )
            yield f"event: handshake_failed\ndata: {err_data}\n\n"
            return

        # Handshake succeeded: confirm live subscription
        snapshot = service.get_atomic_snapshot(chat_id)
        ready_data = json.dumps(
            {
                "status": "connected",
                "epoch_id": snapshot.epoch_id,
                "current_version": snapshot.state_version,
                "zero_replay_active": True,
            }
        )
        yield f"event: live_ready\ndata: {ready_data}\n\n"

        # Emit live heartbeat ping every 10 seconds or until client disconnects
        try:
            for _ in range(6):  # Keep alive cycle
                if await request.is_disconnected():
                    break
                await asyncio.sleep(2.0)
                # Check current version
                latest_snapshot = service.get_atomic_snapshot(chat_id)
                if service.is_event_eligible(
                    event_timestamp_ms=latest_snapshot.snapshot_timestamp_ms,
                    event_version=latest_snapshot.state_version,
                    filter_config=filter_config,
                ):
                    state_data = json.dumps(
                        {
                            "type": "state_version_advanced",
                            "state_version": latest_snapshot.state_version,
                            "status": latest_snapshot.status,
                            "message_count": latest_snapshot.message_count,
                        }
                    )
                    yield f"event: live_delta\ndata: {state_data}\n\n"
                    # Update local filter to advance baseline
                    filter_config.client_state_version = latest_snapshot.state_version
                    filter_config.client_snapshot_timestamp_ms = latest_snapshot.snapshot_timestamp_ms

                ping_data = json.dumps({"type": "ping", "server_time_ms": latest_snapshot.snapshot_timestamp_ms})
                yield f"event: ping\ndata: {ping_data}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
