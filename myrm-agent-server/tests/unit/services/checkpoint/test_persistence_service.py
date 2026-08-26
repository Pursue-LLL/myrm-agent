"""Unit tests for SandboxPersistenceService integration with PrivacyLadderValidator."""

from __future__ import annotations

import asyncio
from pathlib import Path
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

    # Ensure storage.write was called for allowed files + seal manifest
    assert mock_storage.write.call_count == 3
    written_keys = [call[0][0] for call in mock_storage.write.call_args_list]
    assert "sessions/session_abc/chart.png" in written_keys
    assert "sessions/session_abc/report.xlsx" in written_keys
    assert "sessions/session_abc/.seal.json" in written_keys
    assert report.is_sealed is True
    assert report.manifest_file == "sessions/session_abc/.seal.json"


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


@pytest.mark.asyncio
async def test_verify_and_quarantine_corrupted_session(tmp_path: Path) -> None:
    workspace = tmp_path / "restore_workspace"
    workspace.mkdir()

    # Create workspace files
    file_good = workspace / "doc.txt"
    file_good.write_bytes(b"Good content")
    file_bad = workspace / "bad_data.bin"
    file_bad.write_bytes(b"Corrupted bytes")

    # Generate a manifest expecting different content for bad_data.bin
    from myrm_agent_harness.api import IntegritySealer, IntegrityStatus

    valid_files = {
        "doc.txt": b"Good content",
        "bad_data.bin": b"Original untorn bytes",
    }
    manifest = IntegritySealer.create_seal_manifest("sess_restore", valid_files)

    mock_storage = AsyncMock()
    mock_storage.exists.return_value = True
    mock_storage.read.return_value = manifest.to_json().encode("utf-8")

    service = SandboxPersistenceService(storage_backend=mock_storage)

    report = await service.verify_and_quarantine_session(
        session_id="sess_restore",
        workspace_root=workspace,
    )

    assert report.is_valid is False
    assert report.status == IntegrityStatus.CORRUPTED
    assert "bad_data.bin" in report.corrupted_files
    assert report.quarantined is True

    # Ensure corrupted file was moved to quarantine
    quarantine_path = workspace / "quarantine" / "corrupted_sess_restore" / "bad_data.bin"
    assert quarantine_path.exists()
    assert not (workspace / "bad_data.bin").exists()
    assert (workspace / "doc.txt").exists()
