"""REST API for Shell-Free Safe File Descriptor IPC Pipeline.

[INPUT]
- IpcCommandDispatchRequest from app.schemas.ipc_pipeline
- SafeIpcService from app.services.security.safe_ipc_service

[OUTPUT]
- APIRouter mounted under /security/ipc

[POS]
Server API. Provides endpoints for invoking sandbox subcommands and IPC tasks
with guaranteed zero-shell-injection and POSIX 0600 temporary file isolation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.ipc_pipeline import (
    IpcCommandDispatchRequest,
    IpcCommandDispatchResponse,
)
from app.services.security.safe_ipc_service import get_safe_ipc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ipc", tags=["security-ipc"])


@router.post(
    "/dispatch",
    response_model=IpcCommandDispatchResponse,
    summary="Safely dispatch subprocess command with query-file or stdin stream payload",
)
async def dispatch_ipc_command(
    body: IpcCommandDispatchRequest,
) -> IpcCommandDispatchResponse:
    """Execute a subprocess command passing payload via secure 0600 query-file or stdin stream."""
    service = get_safe_ipc_service()
    return await service.dispatch(body)
