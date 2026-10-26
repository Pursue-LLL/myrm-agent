"""Handler coverage for the export half of the import/export lifecycle."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from myrm_agent_harness.toolkits.memory import (
    MemoryArchiveManifest,
    MemoryArchivePayload,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory.operations.crud.import_flows.export_flow import (
    export_memories,
    export_memories_markdown,
    export_memory_archive,
    export_rules_safe,
    preview_rules_safe,
)
from tests.services.memory.import_flows.support import read_stream, session_context


class _ExportManager:
    async def export_all(self) -> dict[str, object]:
        return {
            "semantic": [{"id": "1", "content": "keep"}, "junk"],
            "profile": "not-a-list",
            "bad": [1, 2],
        }


class _RulesManager:
    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results
        self.calls: list[tuple[list[str] | None, str]] = []

    async def export_rules_safe(
        self,
        *,
        rule_ids: list[str] | None,
        output_format: str,
    ) -> list[dict[str, object]]:
        self.calls.append((rule_ids, output_format))
        return self.results


class _MarkdownManager:
    async def export_markdown(self, tmp_dir: str) -> dict[str, int]:
        Path(tmp_dir, "semantic.md").write_text("memory", encoding="utf-8")
        return {"semantic": 1}


@pytest.mark.asyncio
async def test_export_memories_normalizes_entries_and_drops_invalid_rows() -> None:
    response = await export_memories(manager=_ExportManager())  # type: ignore[arg-type]

    assert response.data["semantic"] == [{"id": "1", "content": "keep"}]
    assert response.data["profile"] == []
    assert response.data["bad"] == []
    assert response.total_count == 1


@pytest.mark.asyncio
async def test_export_rules_safe_zips_sanitized_rules() -> None:
    manager = _RulesManager([{"id": "rule-12345678", "rendered": '{"k": 1}'}])

    response = await export_rules_safe(
        manager=manager,  # type: ignore[arg-type]
        rule_ids=" rule-1 , rule-2 ",
        output_format="json",
    )

    assert manager.calls == [(["rule-1", "rule-2"], "json")]
    assert response.headers["X-Export-Count"] == "1"
    with zipfile.ZipFile(io.BytesIO(await read_stream(response))) as archive:
        assert archive.namelist() == ["rule_rule-123.json"]
        assert archive.read("rule_rule-123.json") == b'{"k": 1}'


@pytest.mark.asyncio
async def test_export_rules_safe_rejects_empty_selection() -> None:
    manager = _RulesManager([])

    with pytest.raises(HTTPException) as exc_info:
        await export_rules_safe(manager=manager, rule_ids=None, output_format="markdown")  # type: ignore[arg-type]

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_preview_rules_safe_forwards_parsed_filters() -> None:
    manager = _RulesManager([{"id": "rule-1", "rendered": "x"}])

    result = await preview_rules_safe(
        manager=manager,  # type: ignore[arg-type]
        rule_ids="a,b",
        output_format="markdown",
    )

    assert result == [{"id": "rule-1", "rendered": "x"}]
    assert manager.calls == [(["a", "b"], "markdown")]


@pytest.mark.asyncio
async def test_export_memories_markdown_zips_written_files() -> None:
    response = await export_memories_markdown(manager=_MarkdownManager())  # type: ignore[arg-type]

    assert response.headers["X-Export-Count"] == "1"
    with zipfile.ZipFile(io.BytesIO(await read_stream(response))) as archive:
        assert archive.namelist() == ["semantic.md"]
        assert archive.read("semantic.md") == b"memory"


@pytest.mark.asyncio
async def test_export_memory_archive_records_section_metadata() -> None:
    archive = MemoryArchivePayload(
        manifest=MemoryArchiveManifest(created_at="2026-01-01T00:00:00Z", sections=[]),
        data={},
    )
    record_event = AsyncMock()

    class _FakeArchiveService:
        def __init__(self, _db: object) -> None:
            pass

        async def export_archive(self, _manager: object) -> MemoryArchivePayload:
            return archive

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.export_flow.get_session",
            session_context(cast(AsyncSession, SimpleNamespace())),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.export_flow.MemoryArchiveService",
            _FakeArchiveService,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.export_flow._record_memory_event",
            record_event,
        ),
    ):
        response = await export_memory_archive(manager=_ExportManager())  # type: ignore[arg-type]

    assert response.archive.manifest.version == 1
    record_event.assert_awaited_once()
    assert record_event.await_args.kwargs["metadata"] == {
        "archive_version": 1,
        "section_count": 0,
        "content_redacted": True,
    }
