"""Handler coverage for import rollback preview and execution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.archive import MemoryImportRollbackRequest
from app.services.memory.imports.import_ledger import MemoryImportLedgerService
from app.services.memory.imports.import_sessions import MemoryImportSessionService
from app.services.memory.operations.crud.import_flows.rollback_flow import (
    dry_run_rollback_import_memories,
    rollback_import_memories,
)
from tests.services.memory.import_flows.support import session_context
from tests.services.memory.test_import_sessions import _FakeMemoryManager


@pytest.mark.asyncio
async def test_rollback_preview_and_execution_restore_the_batch(db_session: AsyncSession) -> None:
    fake_manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    dry_run_id, _preview, _hash, _expires = await service.create_dry_run(
        {"data": {"semantic": [{"content": "Rollback restores this.", "metadata": {}}]}},
        "native_json",
    )
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=fake_manager)

    with patch(
        "app.services.memory.operations.crud.import_flows.rollback_flow.get_session",
        session_context(db_session),
    ):
        preview = await dry_run_rollback_import_memories(
            MemoryImportRollbackRequest(import_batch_id=confirm.import_batch_id),
            manager=fake_manager,  # type: ignore[arg-type]
        )
        result = await rollback_import_memories(
            MemoryImportRollbackRequest(import_batch_id=confirm.import_batch_id),
            manager=fake_manager,  # type: ignore[arg-type]
        )

    assert preview.import_batch_id == confirm.import_batch_id
    assert preview.total_items == 1
    assert preview.reversible_items == 1
    assert result.total_rolled_back == 1
    assert result.instructions_rolled_back is False
    assert all(not memory_ids for memory_ids in fake_manager.memory_ids_by_type.values())


@pytest.mark.asyncio
async def test_rollback_replays_cron_jobs_and_deletes_the_imported_agent(
    db_session: AsyncSession,
) -> None:
    fake_manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    dry_run_id, _preview, _hash, _expires = await service.create_dry_run(
        {"data": {"semantic": [{"content": "Delete the agent this import created.", "metadata": {}}]}},
        "native_json",
    )
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=fake_manager)
    cron_rollback = {"created_job_ids": ["job-1"], "failed_count": 0}
    await MemoryImportLedgerService(db_session).merge_batch_metadata(
        confirm.import_batch_id,
        {
            "cron_rollback": cron_rollback,
            "instruction_rollback": {"agent_created": True},
        },
    )
    rollback_cron = AsyncMock()

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.rollback_flow.get_session",
            session_context(db_session),
        ),
        patch(
            "app.services.migration.instruction_rollback.rollback_instruction_for_batch_metadata",
            AsyncMock(return_value=True),
        ) as rollback_instructions,
        patch(
            "app.services.migration.hermes.hermes_cron_migration.rollback_hermes_cron_migration",
            rollback_cron,
        ),
    ):
        result = await rollback_import_memories(
            MemoryImportRollbackRequest(
                import_batch_id=confirm.import_batch_id,
                delete_imported_agent=True,
            ),
            manager=fake_manager,  # type: ignore[arg-type]
        )

    assert result.instructions_rolled_back is True
    assert result.imported_agent_deleted is True
    rollback_instructions.assert_awaited_once()
    rollback_cron.assert_awaited_once_with(cron_rollback)


@pytest.mark.asyncio
async def test_rollback_maps_unknown_batch_to_http_error(db_session: AsyncSession) -> None:
    request = MemoryImportRollbackRequest(import_batch_id="memory-import-batch:missing")

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.rollback_flow.get_session",
            session_context(db_session),
        ),
        pytest.raises(HTTPException) as preview_error,
    ):
        await dry_run_rollback_import_memories(
            request,
            manager=_FakeMemoryManager(),  # type: ignore[arg-type]
        )

    assert preview_error.value.status_code in {404, 409}

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.rollback_flow.get_session",
            session_context(db_session),
        ),
        pytest.raises(HTTPException) as rollback_error,
    ):
        await rollback_import_memories(
            request,
            manager=_FakeMemoryManager(),  # type: ignore[arg-type]
        )

    assert rollback_error.value.status_code in {404, 409}
