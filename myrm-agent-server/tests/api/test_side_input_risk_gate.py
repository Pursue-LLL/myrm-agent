"""The boxes beside the chat input refuse a secret before anything is stored or any model reads it.

Regeneration guidance, the session advisor question, the wiki question and the titles of a decomposed task are typed like
a chat message and end in a model's context. Each runs its real route handler with only the detection rules injected; a
refusal is HTTP 400 with the ``risk_held`` code, and the state the endpoint would have changed is left as it was.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chats.chat.copilot import router as copilot_router
from app.api.chats.chat.turn import router as turn_router
from app.api.kanban.router import router as kanban_router
from app.api.wiki.router import _get_wiki_archiver
from app.api.wiki.router import router as wiki_router
from app.database.connection import get_db
from app.database.models import Message
from app.services.chat.chat_service import ChatService
from app.services.copilot.advisor_thread_store import AdvisorThreadStore
from app.services.kanban import KanbanService
from app.services.risk.refusal import RISK_HELD_CODE
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture(autouse=True)
def _risk_rules() -> Iterator[None]:
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        yield


class _HttpResponse(Protocol):
    """The part of a client response these tests read; the sync and async ``httpx`` clients both provide it."""

    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> dict[str, dict[str, object]]: ...


def _assert_held(response: _HttpResponse) -> None:
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == RISK_HELD_CODE
    assert detail["rules"] == [{"rule_id": "r-apikey", "display_name": "API Key Leak", "severity": "critical"}]
    assert SECRET not in response.text


# --- regeneration guidance ---------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _checkpoint_sync_is_not_under_test() -> Iterator[None]:
    with patch("app.services.chat.chat_turn._ChatTurnMixin._sync_checkpoint_after_mutation", new_callable=AsyncMock):
        yield


@pytest_asyncio.fixture
async def regenerate_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app = FastAPI()
    app.include_router(turn_router, prefix="/chats")
    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _seed_one_answer(chat_id: str) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="summarise the report",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id=f"{chat_id}-user",
    )
    await ChatService.persist_assistant_message_safe(chat_id=chat_id, content="first answer", extra_data={})


async def _active_answers(db: AsyncSession, chat_id: str) -> list[str]:
    await db.rollback()
    rows = await db.execute(
        select(Message.content).where(Message.chat_id == chat_id, Message.role == "assistant", Message.is_active.is_(True))
    )
    return list(rows.scalars())


@pytest.mark.asyncio
async def test_regeneration_guidance_with_a_secret_is_refused_and_the_answer_stays_active(
    regenerate_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_one_answer("chat-regen-held")

    _assert_held(await regenerate_client.post("/chats/chat-regen-held/regenerate", json={"instruction": f"use {SECRET}"}))

    assert await _active_answers(db_session, "chat-regen-held") == ["first answer"]


@pytest.mark.asyncio
async def test_regeneration_with_clean_guidance_sets_the_answer_aside(
    regenerate_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_one_answer("chat-regen-clean")

    response = await regenerate_client.post("/chats/chat-regen-clean/regenerate", json={"instruction": "be more concise"})

    assert response.status_code == 200
    assert response.json()["data"]["instruction"] == "be more concise"
    assert await _active_answers(db_session, "chat-regen-clean") == []


@pytest.mark.asyncio
async def test_regeneration_without_guidance_is_not_screened(regenerate_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_one_answer("chat-regen-plain")

    assert (await regenerate_client.post("/chats/chat-regen-plain/regenerate")).status_code == 200


# --- session advisor ---------------------------------------------------------------------------------------------


@pytest.fixture
def advisor_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(copilot_router, prefix="/chats")
    AdvisorThreadStore.clear("chat-advisor")
    with TestClient(app) as client:
        yield client
    AdvisorThreadStore.clear("chat-advisor")


def test_advisor_question_with_a_secret_is_refused_and_neither_stored_nor_asked(advisor_client: TestClient) -> None:
    with patch("app.api.chats.chat.copilot.ask_advisor", new_callable=AsyncMock) as ask:
        _assert_held(advisor_client.post("/chats/chat-advisor/copilot/advisor/ask", json={"question": f"is {SECRET} valid"}))

    ask.assert_not_awaited()
    assert AdvisorThreadStore.list_messages("chat-advisor") == []


def test_advisor_clean_question_is_stored_and_answered(advisor_client: TestClient) -> None:
    with patch("app.api.chats.chat.copilot.ask_advisor", new_callable=AsyncMock, return_value=("a reply", "tier0")):
        response = advisor_client.post("/chats/chat-advisor/copilot/advisor/ask", json={"question": "what is left to do"})

    assert response.status_code == 200
    assert [m.role for m in AdvisorThreadStore.list_messages("chat-advisor")] == ["user", "assistant"]


# --- wiki question -----------------------------------------------------------------------------------------------


@pytest.fixture
def wiki_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(wiki_router, prefix="/wiki")
    app.dependency_overrides[_get_wiki_archiver] = lambda: MagicMock()
    with TestClient(app) as client:
        yield client


def test_wiki_question_with_a_secret_is_refused_before_any_retrieval(wiki_client: TestClient) -> None:
    """The refusal is a 400, not the 500 the handler turns any exception raised inside its own try into."""
    with patch("app.services.wiki.knowledge_query_service.execute_wiki_knowledge_query", new_callable=AsyncMock) as query:
        _assert_held(wiki_client.post("/wiki/query", json={"question": f"what does {SECRET} unlock"}))

    query.assert_not_awaited()


def test_wiki_clean_question_reaches_the_knowledge_query(wiki_client: TestClient) -> None:
    result = MagicMock(answer="an answer", related_articles=[], sources=[], confidence_score=0.9, refused=False)
    result.retrieval_result.retrieval_trace = None
    with patch(
        "app.services.wiki.knowledge_query_service.execute_wiki_knowledge_query", new_callable=AsyncMock, return_value=result
    ) as query:
        response = wiki_client.post("/wiki/query", json={"question": "how do we deploy"})

    assert response.status_code == 200
    query.assert_awaited_once()


# --- decomposed task titles --------------------------------------------------------------------------------------


@pytest.fixture
def kanban_client() -> Iterator[TestClient]:
    KanbanService._instance = None
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with (
        patch.object(KanbanService, "_validate_agent_id", new_callable=AsyncMock),
        TestClient(app) as client,
    ):
        yield client
    KanbanService._instance = None


def _triage_task(client: TestClient) -> tuple[str, str]:
    board_id = str(client.post("/api/v1/kanban/boards", json={"name": "Board"}).json()["board_id"])
    task_id = str(client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": "plan the launch"}).json()["task_id"])

    async def _set() -> None:
        service = KanbanService.get_instance()
        task = await service.get_task(task_id)
        assert task is not None
        task.status = TaskStatus.TRIAGE
        await service.store.save_task(task)

    asyncio.run(_set())
    return board_id, task_id


def _task_count(client: TestClient, board_id: str) -> int:
    return len(client.get(f"/api/v1/kanban/boards/{board_id}/tasks").json()["items"])


def _children(*titles: str) -> dict[str, object]:
    return {"fanout": True, "children": [{"title": title, "body": "the model's text"} for title in titles]}


def test_decomposed_child_title_with_a_secret_is_refused_and_no_child_is_created(kanban_client: TestClient) -> None:
    board_id, task_id = _triage_task(kanban_client)

    _assert_held(
        kanban_client.post(
            f"/api/v1/kanban/tasks/{task_id}/apply-decompose", json=_children("write the copy", f"deploy with {SECRET}")
        )
    )

    assert _task_count(kanban_client, board_id) == 1


def test_decomposed_children_with_clean_titles_are_created(kanban_client: TestClient) -> None:
    board_id, task_id = _triage_task(kanban_client)

    response = kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/apply-decompose", json=_children("write the copy", "ship it"))

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert _task_count(kanban_client, board_id) == 3


def test_decomposed_child_body_is_the_models_text_and_is_not_screened(kanban_client: TestClient) -> None:
    """The dialog shows the body read-only, so a refusal on it would leave the user nothing to edit."""
    board_id, task_id = _triage_task(kanban_client)
    children = {"fanout": True, "children": [{"title": "write the copy", "body": f"quote: {SECRET}"}]}

    response = kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/apply-decompose", json=children)

    assert response.status_code == 200
    assert _task_count(kanban_client, board_id) == 2
