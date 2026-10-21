"""Live meeting notes REST contract tests (error paths, lifecycle, agent scoping).

Covers the HTTP surface the voice Live board depends on: request validation,
unknown/expired sessions, double finalize, the real frontend default
(`auto_compile=true`), per-agent vault routing, and degradation when the LLM fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.meeting_notes.live_notes import get_live_notes_registry
from app.services.meeting_notes.models import StructuredMeetingNotes
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app

_MEETING_LINES = (
    "Alice: Let us confirm the release plan. The beta goes live on Friday so marketing "
    "has the weekend to prepare the announcement.",
    "Bob: The transcription vendor contract expired last month and legal review is still "
    "pending, so nobody has signed it off.",
    "Carol: I will draft the migration checklist before Thursday and Alice will decide on "
    "Friday morning.",
)


@pytest.fixture(autouse=True)
def _bypass_auth() -> Any:
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class _FakeIdentity:
        user_id: str = LOCAL_USER_ID
        auth_source: str = "loopback"
        loopback: bool = True
        client_ip: str = "127.0.0.1"
        private_net: bool = False

    with patch("app.middleware.auth.resolve_identity", return_value=_FakeIdentity()):
        yield


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


def _build_client(tmp_path: Path) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(tmp_path / "wiki"))
    archiver._structure.ensure_structure()
    archiver._llm = _fake_llm()
    archiver._compiler = MagicMock()
    archiver._compiler._queue = MagicMock()

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    return TestClient(app), archiver, archiver._structure


def _ingest_all(client: TestClient, session_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for index, line in enumerate(_MEETING_LINES):
        response = client.post(
            f"/api/v1/wiki/meeting-notes/live/{session_id}/ingest",
            json={"text": line, "timestamp": index * 10.0, "line_id": f"{session_id}-{index}"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
    return payload


# -- request validation ------------------------------------------------------
def test_ingest_requires_line_id(client: TestClient, tmp_path: Path) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
    response = client.post(
        "/api/v1/wiki/meeting-notes/live/s1/ingest", json={"text": "hello"}
    )
    assert response.status_code == 422
    assert any(err["loc"][-1] == "line_id" for err in response.json()["detail"])


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "", "line_id": "l1"},
        {"text": "   ", "line_id": "l1"},
        {"text": "hello", "line_id": ""},
        {"text": "hello", "line_id": "x" * 65},
        {"text": "hello", "line_id": "l1", "timestamp": -1},
    ],
)
def test_ingest_rejects_malformed_payloads(
    client: TestClient, tmp_path: Path, payload: dict[str, Any]
) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
    response = client.post("/api/v1/wiki/meeting-notes/live/s1/ingest", json=payload)
    assert response.status_code == 422, response.text


# -- lifecycle ---------------------------------------------------------------
def test_snapshot_and_finalize_of_unknown_session_are_404(
    client: TestClient, tmp_path: Path
) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
    assert client.get("/api/v1/wiki/meeting-notes/live/nope").status_code == 404
    assert client.post("/api/v1/wiki/meeting-notes/live/nope/finalize").status_code == 404


def test_ingest_is_idempotent_over_http(client: TestClient, tmp_path: Path) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
    body = {"text": "Alice: one line only", "timestamp": 0.0, "line_id": "same-id"}
    first = client.post("/api/v1/wiki/meeting-notes/live/s/ingest", json=body).json()
    replay = client.post("/api/v1/wiki/meeting-notes/live/s/ingest", json=body).json()
    assert first["line_count"] == 1
    assert replay["line_count"] == 1
    assert replay["transcript_chars"] == first["transcript_chars"]


def test_finalize_publishes_releases_and_second_finalize_is_404(
    client: TestClient, tmp_path: Path
) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
    _ingest_all(client, "lifecycle")
    final = client.post("/api/v1/wiki/meeting-notes/live/lifecycle/finalize")
    assert final.status_code == 200, final.text
    body = final.json()
    assert body["title"] == "Release Plan Review"
    assert body["risks"] == ["Vendor contract unsigned"]
    assert body["action_items"][0]["owner"] == "Bob"
    assert body["published_wiki_paths"] == [
        "meeting-notes/meeting-Release_Plan_Review.md"
    ]
    assert client.get("/api/v1/wiki/meeting-notes/live/lifecycle").status_code == 404
    assert client.post("/api/v1/wiki/meeting-notes/live/lifecycle/finalize").status_code == 404


def test_finalize_honours_auto_compile_default_from_the_frontend(
    client: TestClient, tmp_path: Path
) -> None:
    """The voice board finalizes without the query flag, i.e. auto_compile defaults on."""
    client, archiver, _structure = _build_client(tmp_path)
    enqueue = archiver._compiler._queue
    _ingest_all(client, "compile-default")
    assert client.post("/api/v1/wiki/meeting-notes/live/compile-default/finalize").status_code == 200
    enqueue.enqueue_file.assert_called_once()


def test_ingest_after_finalize_starts_a_fresh_session(
    client: TestClient, tmp_path: Path
) -> None:
    """A straggler STT line must not resurrect or corrupt the published minutes."""
    client, _archiver, structure = _build_client(tmp_path)
    _ingest_all(client, "straggler")
    client.post("/api/v1/wiki/meeting-notes/live/straggler/finalize?auto_compile=false")
    response = client.post(
        "/api/v1/wiki/meeting-notes/live/straggler/ingest",
        json={"text": "late line", "line_id": "late-1"},
    )
    assert response.status_code == 200
    assert response.json()["line_count"] == 1
    published = list((structure.raw_dir / "meeting-notes").glob("*.md"))
    assert len(published) == 1
    assert "late line" not in published[0].read_text(encoding="utf-8")


def test_collision_suffixes_the_second_meeting(client: TestClient, tmp_path: Path) -> None:
    client, _archiver, structure = _build_client(tmp_path)
    for session in ("first", "second"):
        _ingest_all(client, session)
        assert client.post(
            f"/api/v1/wiki/meeting-notes/live/{session}/finalize?auto_compile=false"
        ).status_code == 200
    names = sorted(p.name for p in (structure.raw_dir / "meeting-notes").glob("*.md"))
    assert names == ["meeting-Release_Plan_Review-2.md", "meeting-Release_Plan_Review.md"]


def test_distillation_failure_does_not_break_ingest_or_finalize(
    client: TestClient, tmp_path: Path
) -> None:
    """A dead LLM must still record the transcript and still publish raw minutes."""
    client, archiver, structure = _build_client(tmp_path)
    archiver._llm = MagicMock()
    archiver._llm.ainvoke.side_effect = RuntimeError("llm down")

    _ingest_all(client, "llm-down")
    final = client.post("/api/v1/wiki/meeting-notes/live/llm-down/finalize?auto_compile=false")
    assert final.status_code == 500

    # With the LLM still dead the session must be recoverable, not wedged.
    recovered = client.post("/api/v1/wiki/meeting-notes/live/llm-down/ingest", json={
        "text": "Dave: still here", "line_id": "d1"
    })
    assert recovered.status_code == 200
    assert recovered.json()["line_count"] == 4
    assert structure.raw_dir.exists()


def test_malformed_llm_payload_still_yields_publishable_minutes(
    client: TestClient, tmp_path: Path
) -> None:
    """A chatty model (string where a list belongs) must not corrupt the minutes."""
    client, archiver, structure = _build_client(tmp_path)
    archiver._llm.ainvoke.return_value = MagicMock(
        content=json.dumps(
            {
                "title": None,
                "summary": "Rough notes",
                "risks": "vendor contract expired",
                "action_items": None,
            }
        )
    )
    _ingest_all(client, "ragged")
    final = client.post("/api/v1/wiki/meeting-notes/live/ragged/finalize?auto_compile=false")
    assert final.status_code == 200, final.text
    body = final.json()
    assert body["title"] == "Meeting Notes"
    assert body["risks"] == ["vendor contract expired"]
    assert body["action_items"] == []
    markdown = next((structure.raw_dir / "meeting-notes").glob("*.md")).read_text(encoding="utf-8")
    assert "- vendor contract expired" in markdown
    assert "None" not in markdown.split("## Transcript")[0]


def test_registry_drops_finished_sessions(client: TestClient, tmp_path: Path) -> None:
    """Finalize must release the session so a long-lived process cannot leak meetings."""
    import asyncio

    client, _archiver, _structure = _build_client(tmp_path)
    _ingest_all(client, "released")
    client.post("/api/v1/wiki/meeting-notes/live/released/finalize?auto_compile=false")
    assert asyncio.run(get_live_notes_registry().get("released")) is None


def test_published_minutes_carry_no_absolute_local_path(
    client: TestClient, tmp_path: Path
) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
    _ingest_all(client, "no-leak")
    final = client.post("/api/v1/wiki/meeting-notes/live/no-leak/finalize?auto_compile=false")
    for entry in final.json()["published_wiki_paths"]:
        assert isinstance(entry, str)
        assert entry.startswith("meeting-notes/")
        assert str(tmp_path) not in entry


def test_publish_is_skipped_when_no_notes_were_distilled(
    client: TestClient, tmp_path: Path
) -> None:
    """Finalizing an empty session must not fabricate a minutes file."""
    client, _archiver, structure = _build_client(tmp_path)
    response = client.post(
        "/api/v1/wiki/meeting-notes/live/empty/finalize?auto_compile=false"
    )
    assert response.status_code == 404
    assert not (structure.raw_dir / "meeting-notes").exists()
    assert StructuredMeetingNotes is not None
