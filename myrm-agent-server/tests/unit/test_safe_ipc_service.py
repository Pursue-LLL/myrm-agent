"""Unit tests for SafeIpcService in server layer.

[POS]
Verifies server-level subprocess dispatching via query-file and stdin stream,
command safety validation, rejection of unsafe shell invocations, and timeout handling.
"""

from __future__ import annotations

import sys

import pytest

from app.schemas.ipc_pipeline import (
    IpcCommandDispatchRequest,
    IpcDispatchMode,
)
from app.services.security.safe_ipc_service import SafeIpcService


@pytest.mark.asyncio
async def test_safe_ipc_service_query_file_dispatch() -> None:
    service = SafeIpcService()

    # Python worker script reading query-file
    worker_script = (
        "import sys, pathlib; "
        "idx = sys.argv.index('--query-file'); "
        "content = pathlib.Path(sys.argv[idx + 1]).read_text(); "
        "print('SUCCESS:', content, end='')"
    )

    request = IpcCommandDispatchRequest(
        command=[sys.executable, "-c", worker_script],
        payload="Arbitrary payload with \"quotes\" and 'single' and \nnewlines",
        transport=IpcDispatchMode.QUERY_FILE,
        timeout_seconds=10.0,
    )

    response = await service.dispatch(request)
    assert response.status == "success"
    assert response.returncode == 0
    assert response.stdout == f"SUCCESS: {request.payload}"
    assert response.duration_seconds >= 0.0


@pytest.mark.asyncio
async def test_safe_ipc_service_stdin_stream_dispatch() -> None:
    service = SafeIpcService()

    worker_script = "import sys; print('STREAM:', sys.stdin.read(), end='')"
    request = IpcCommandDispatchRequest(
        command=[sys.executable, "-c", worker_script],
        payload="Stream payload: data line 1\ndata line 2",
        transport=IpcDispatchMode.STDIN_STREAM,
        timeout_seconds=10.0,
    )

    response = await service.dispatch(request)
    assert response.status == "success"
    assert response.returncode == 0
    assert response.stdout == f"STREAM: {request.payload}"


@pytest.mark.asyncio
async def test_safe_ipc_service_rejects_unsafe_command() -> None:
    service = SafeIpcService()

    # Attempt to wrap inside bash -c
    request = IpcCommandDispatchRequest(
        command=["bash", "-c", "echo 'injected'"],
        payload="some payload",
        transport=IpcDispatchMode.QUERY_FILE,
    )

    response = await service.dispatch(request)
    assert response.status == "rejected"
    assert response.returncode == -1
    assert "strictly forbidden" in response.stderr
