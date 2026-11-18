"""Small helpers shared by the import-flow handler tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.database.models.memory import MemoryImportDryRunModel
from app.schemas.memory.archive import MemoryImportDryRunRequest
from app.services.memory.operations.crud.import_flows.dry_run import dry_run_import_memories


def session_context(session: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Patch a handler's ``get_session`` dependency with one fixed session."""

    @asynccontextmanager
    async def _context() -> AsyncIterator[AsyncSession]:
        yield session

    return _context


async def read_stream(response: StreamingResponse) -> bytes:
    """Drain a streaming response into the bytes a ZIP reader can consume."""

    return b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[misc]


async def persisted_review_session(
    db_session: AsyncSession,
    competitor: str,
    loaded_payload: dict[str, object],
) -> MemoryImportDryRunModel:
    """Run a competitor dry run over ``loaded_payload`` and return the review session row it stored."""

    with (
        patch(
            "app.services.migration.source.source_payload_loader.load_source_payload",
            return_value={"_source": competitor, **loaded_payload},
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.get_session",
            session_context(db_session),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.external_source_providers_configured",
            AsyncMock(return_value=False),
        ),
    ):
        response = await dry_run_import_memories(
            MemoryImportDryRunRequest(payload={"competitor": competitor, "root": f"/tmp/{competitor}"}),
        )
    return (
        await db_session.execute(select(MemoryImportDryRunModel).where(MemoryImportDryRunModel.id == response.dry_run_id))
    ).scalar_one()


def stored_columns_text(row: MemoryImportDryRunModel) -> str:
    """Every payload column of a review session row as one searchable text."""

    columns = [row.normalized_data_json, row.summary_json, row.warnings_json, row.metadata_json]
    return json.dumps(columns, default=str)
