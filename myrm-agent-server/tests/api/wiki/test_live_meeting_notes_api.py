"""Live meeting notes REST contract tests (error paths, lifecycle, agent scoping).

Covers the HTTP surface the voice Live board depends on: request validation,
unknown/expired sessions, double finalize, the real frontend default
(`auto_compile=true`), per-agent vault routing, and degradation when the LLM fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Query
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


def _make_archiver(wiki_dir: Path) -> MemoryToWikiArchiver:
    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(wiki_dir))
    archiver._structure.ensure_structure()
    archiver._llm = _fake_llm()
    archiver._compiler = MagicMock()
    archiver._compiler._queue = MagicMock()
    return archiver


def _build_client(tmp_path: Path) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = _make_archiver(tmp_path / "wiki")

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
def test_finalize_of_unknown_session_is_404(client: TestClient, tmp_path: Path) -> None:
    client, _archiver, _structure = _build_client(tmp_path)
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


def test_finalize_publishes_into_the_vault_of_the_requested_agent(tmp_path: Path) -> None:
    """The vault comes from the scoped archiver dependency; finalize needs no agent id of its own."""
    from app.api.wiki.router import _get_wiki_archiver

    default_archiver = _make_archiver(tmp_path / "default")
    agent_archiver = _make_archiver(tmp_path / "agent-b")
    app = build_minimal_app(preset="wiki")

    async def _scoped(agent_id: Annotated[str | None, Query()] = None) -> MemoryToWikiArchiver:
        return agent_archiver if agent_id == "agent-b" else default_archiver

    app.dependency_overrides[_get_wiki_archiver] = _scoped
    client = TestClient(app)
    _ingest_all(client, "agent-scoped")

    final = client.post("/api/v1/wiki/meeting-notes/live/agent-scoped/finalize?agent_id=agent-b&auto_compile=false")

    assert final.status_code == 200, final.text
    assert list((agent_archiver._structure.raw_dir / "meeting-notes").glob("*.md"))
    assert not (default_archiver._structure.raw_dir / "meeting-notes").exists()


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


def test_distillation_failure_fails_finalize_but_keeps_the_session_recoverable(
    client: TestClient, tmp_path: Path
) -> None:
    """A dead LLM fails finalize without publishing, yet the session keeps recording."""
    client, archiver, structure = _build_client(tmp_path)
    archiver._llm = MagicMock()
    archiver._llm.ainvoke.side_effect = RuntimeError("llm down")

    _ingest_all(client, "llm-down")
    final = client.post("/api/v1/wiki/meeting-notes/live/llm-down/finalize?auto_compile=false")
    assert final.status_code == 500
    assert not (structure.raw_dir / "meeting-notes").exists()

    # With the LLM still dead the session must be recoverable, not wedged.
    recovered = client.post("/api/v1/wiki/meeting-notes/live/llm-down/ingest", json={
        "text": "Dave: still here", "line_id": "d1"
    })
    assert recovered.status_code == 200
    assert recovered.json()["line_count"] == 4


def test_failed_finalize_can_be_retried_once_the_llm_is_back(
    client: TestClient, tmp_path: Path
) -> None:
    """A failed run is forgotten: the retry runs afresh and publishes the meeting exactly once."""
    client, archiver, structure = _build_client(tmp_path)
    working_llm = archiver._llm
    archiver._llm = MagicMock()
    archiver._llm.ainvoke.side_effect = RuntimeError("llm down")
    _ingest_all(client, "retry")
    url = "/api/v1/wiki/meeting-notes/live/retry/finalize?auto_compile=false"
    assert client.post(url).status_code == 500

    archiver._llm = working_llm
    retried = client.post(url)

    assert retried.status_code == 200, retried.text
    assert retried.json()["published_wiki_paths"] == ["meeting-notes/meeting-Release_Plan_Review.md"]
    assert len(list((structure.raw_dir / "meeting-notes").glob("*.md"))) == 1


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


async def test_concurrent_finalize_publishes_the_meeting_once(tmp_path: Path) -> None:
    """A double stop (two requests racing) must share one run, not publish the meeting twice."""
    import asyncio

    import httpx

    client, archiver, structure = _build_client(tmp_path)
    started = asyncio.Event()
    gate = asyncio.Event()
    distilled = archiver._llm.ainvoke.return_value

    async def slow_ainvoke(_prompt: str) -> MagicMock:
        started.set()
        await gate.wait()
        return distilled

    url = "/api/v1/wiki/meeting-notes/live/double-stop/finalize?auto_compile=false"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://test") as http:
        for index, line in enumerate(_MEETING_LINES):
            ingested = await http.post(
                "/api/v1/wiki/meeting-notes/live/double-stop/ingest",
                json={"text": line, "timestamp": index * 10.0, "line_id": f"double-stop-{index}"},
            )
            assert ingested.status_code == 200, ingested.text
        archiver._llm.ainvoke.side_effect = slow_ainvoke
        archiver._llm.ainvoke.reset_mock()

        first = asyncio.create_task(http.post(url))
        await started.wait()
        second = asyncio.create_task(http.post(url))
        await asyncio.sleep(0.05)
        gate.set()
        responses = await asyncio.gather(first, second)

    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    assert archiver._llm.ainvoke.call_count == 1
    assert len(list((structure.raw_dir / "meeting-notes").glob("*.md"))) == 1


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
