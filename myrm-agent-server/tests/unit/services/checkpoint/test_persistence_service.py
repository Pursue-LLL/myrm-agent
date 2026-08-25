"""Unit tests for SandboxPersistenceService integration with PrivacyLadderValidator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.checkpoint.persistence_service import (
    SandboxPersistenceService,
    get_sandbox_persistence_service,
)
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus


@pytest.mark.asyncio
async def test_persist_session_turn_privacy_filtration(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # 1. Create valid files
    chart_file = workspace / "chart.png"
    chart_file.write_bytes(b"PNG_DATA")
    report_file = workspace / "report.xlsx"
    report_file.write_bytes(b"XLSX_DATA")

    # 2. Create sensitive / dangerous files (should be blocked by fail-closed ladder)
    env_file = workspace / ".env"
    env_file.write_text("SECRET_KEY=12345")
    key_file = workspace / "id_rsa"
    key_file.write_text("PRIVATE_KEY")

    # 3. Create transient cache files (should be ignored)
    cache_dir = workspace / "__pycache__"
    cache_dir.mkdir()
    pyc_file = cache_dir / "mod.pyc"
    pyc_file.write_bytes(b"BYTECODE")

    # Mock storage backend
    mock_storage = AsyncMock()
    service = SandboxPersistenceService(storage_backend=mock_storage)

    report = await service.persist_session_turn(
        session_id="session_abc",
        workspace_root=workspace,
    )

    # Check synced files
    assert "chart.png" in report.synced_files
    assert "report.xlsx" in report.synced_files
    assert ".env" not in report.synced_files
    assert "id_rsa" not in report.synced_files

    # Check blocked files
    blocked_names = [Path(p).name for p, _ in report.blocked_files]
    assert ".env" in blocked_names
    assert "id_rsa" in blocked_names

    # Check ignored files
    ignored_names = [Path(p).name for p in report.ignored_files]
    assert "mod.pyc" in ignored_names

    # Ensure storage.write was called only for allowed files
    assert mock_storage.write.call_count == 2
    written_keys = [call[0][0] for call in mock_storage.write.call_args_list]
    assert "sessions/session_abc/chart.png" in written_keys
    assert "sessions/session_abc/report.xlsx" in written_keys


@pytest.mark.asyncio
async def test_event_driven_trigger_integration(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out_file = workspace / "result.txt"
    out_file.write_text("success")

    mock_storage = AsyncMock()
    service = get_sandbox_persistence_service()
    service.bind_storage_backend(mock_storage)

    bus = get_event_bus()

    # Emit event
    bus.publish(
        AppEvent(
            event_type=AppEventType.SANDBOX_PERSIST_TRIGGERED,
            data={
                "session_id": "event_sess_1",
                "workspace_root": str(workspace),
            },
        )
    )

    # Allow event loop task to run
    await asyncio.sleep(0.1)

    assert mock_storage.write.call_count >= 1
