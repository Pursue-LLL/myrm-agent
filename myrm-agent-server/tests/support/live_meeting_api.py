"""Builders for the REST tests of the live meeting notes endpoints.

[INPUT]
- app.api.wiki.router::_get_wiki_archiver (POS: the wiki archiver dependency the tests override)
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: publishes the distilled minutes into the wiki vault)
- tests.support.minimal_app::build_minimal_app (POS: test-only FastAPI factory mounting just the routes under test)

[OUTPUT]
- MEETING_LINES / ingest_all: a three-speaker transcript and the requests that feed it to one session
- make_archiver / build_client: an archiver on a temporary vault with a canned LLM, and a client wired to it
- double: the Mock that make_archiver put behind a member typed as a real class

[POS]
Server pytest-only helpers shared by ``test_live_meeting_notes_api.py`` and ``test_live_meeting_notes_api_logging.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app

MEETING_LINES = (
    "Alice: Let us confirm the release plan. The beta goes live on Friday so marketing "
    "has the weekend to prepare the announcement.",
    "Bob: The transcription vendor contract expired last month and legal review is still "
    "pending, so nobody has signed it off.",
    "Carol: I will draft the migration checklist before Thursday and Alice will decide on "
    "Friday morning.",
)


def double(value: object) -> Mock:
    """The test double `make_archiver` put where production code types a real class."""
    assert isinstance(value, Mock), value
    return value


def _fake_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.ainvoke.return_value = MagicMock(
        content=json.dumps(
            {
                "title": "Release Plan Review",
                "summary": "The team reviewed the beta release plan.",
                "decisions": ["Ship on Friday"],
                "risks": ["Vendor contract unsigned"],
                "action_items": [{"description": "Sign the contract", "owner": "Bob"}],
            }
        )
    )
    return llm


def make_archiver(wiki_dir: Path) -> MemoryToWikiArchiver:
    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(wiki_dir))
    archiver._structure.ensure_structure()
    archiver._llm = _fake_llm()
    archiver._compiler = MagicMock()
    archiver._compiler._queue = MagicMock()
    return archiver


def build_client(tmp_path: Path) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = make_archiver(tmp_path / "wiki")

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    return TestClient(app), archiver, archiver._structure


def ingest_all(client: TestClient, session_id: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    for index, line in enumerate(MEETING_LINES):
        response = client.post(
            f"/api/v1/wiki/meeting-notes/live/{session_id}/ingest",
            json={"text": line, "timestamp": index * 10.0, "line_id": f"{session_id}-{index}"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
    return payload
