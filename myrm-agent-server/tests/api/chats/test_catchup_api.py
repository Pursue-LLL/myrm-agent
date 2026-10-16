"""Catchup API: which chats the user has not caught up with, their status, and read marking.

``Chat.last_read_at`` is the user's last presence in a chat. An agent reply newer than it is unseen;
a running turn, a pending approval and an unseen failure also need the user. Rows are seeded with
explicit timestamps so the ordering never depends on the clock resolution of the test machine.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from sqlalchemy import select

from app.database.models.approval import ApprovalRecord
from app.database.models.chat import Chat, Message
from app.platform_utils import get_session_factory
from app.services.agent.gateway import get_agent_gateway
from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX
from app.services.copilot.run_digest_store import RunDigestStore
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


def _ago(minutes: int) -> datetime:
    """Naive UTC, the convention ``Message.created_at`` and ``last_read_at`` are stored in."""
    return datetime.utcnow() - timedelta(minutes=minutes)


@pytest.fixture
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        timeout=60.0,
    ) as client:
        yield client


@pytest.fixture
def digest_chats() -> Iterator[list[str]]:
    """Chats whose run digest a test seeded; the digest store is process-wide, so they are cleared afterwards."""
    chat_ids: list[str] = []
    yield chat_ids
    for chat_id in chat_ids:
        RunDigestStore.clear(chat_id)


async def _seed_chat(
    *,
    last_read_minutes_ago: int | None,
    messages: tuple[tuple[str, str, int], ...] = (),
    source: str = "web",
    deleted: bool = False,
    message_ids: tuple[str, ...] = (),
) -> str:
    """Create a chat; each message is (role, content, minutes_ago). ``message_ids`` optionally overrides row ids."""
    chat_id = f"catchup-{uuid.uuid4().hex[:10]}"
    async with get_session_factory()() as db:
        db.add(
            Chat(
                id=chat_id,
                title="Quarterly report",
                action_mode="fast",
                source=source,
                created_at=_ago(120),
                updated_at=_ago(1),
                last_read_at=_ago(last_read_minutes_ago) if last_read_minutes_ago is not None else None,
                deleted_at=_ago(1) if deleted else None,
            )
        )
        await db.flush()
        for index, (role, content, minutes_ago) in enumerate(messages):
            db.add(
                Message(
                    id=message_ids[index] if message_ids else f"msg-{uuid.uuid4().hex[:10]}",
                    chat_id=chat_id,
                    role=role,
                    content=content,
                    sent_at=_ago(minutes_ago),
                    sent_timezone="UTC",
                    created_at=_ago(minutes_ago),
                )
            )
        await db.commit()
    return chat_id


async def _add_pending_approval(chat_id: str) -> None:
    async with get_session_factory()() as db:
        db.add(
            ApprovalRecord(
                id=f"ap-{uuid.uuid4().hex[:8]}",
                agent_id="default",
                chat_id=chat_id,
                action_type="shell_command",
                status="PENDING",
                payload={},
            )
        )
        await db.commit()


async def _briefs(client: httpx.AsyncClient) -> dict[str, dict[str, object]]:
    response = await client.get("/api/v1/chats/catchup")
    assert response.status_code == 200
    return {brief["chat_id"]: brief for brief in response.json()["data"]["briefs"]}


async def _status(client: httpx.AsyncClient, chat_id: str) -> object:
    brief = (await _briefs(client)).get(chat_id)
    return brief["status"] if brief else None


@pytest.mark.asyncio
async def test_a_reply_that_arrived_while_the_user_was_away_is_unseen(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(
        last_read_minutes_ago=10,
        messages=(("user", "Summarise the report", 11), ("assistant", "The report is ready.", 5)),
    )

    brief = (await _briefs(async_client))[chat_id]

    assert brief["status"] == "completed"
    assert brief["last_user_prompt"] == "Summarise the report"
    assert brief["result_preview"] == "The report is ready."
    assert brief["chat_title"] == "Quarterly report"


@pytest.mark.asyncio
async def test_updated_at_names_its_utc_offset_so_a_browser_does_not_read_it_as_local_time(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = await _seed_chat(
        last_read_minutes_ago=10,
        messages=(("user", "Summarise the report", 11), ("assistant", "The report is ready.", 5)),
    )

    updated_at = datetime.fromisoformat(str((await _briefs(async_client))[chat_id]["updated_at"]))

    assert updated_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - updated_at) < timedelta(minutes=3)


@pytest.mark.asyncio
async def test_a_reply_the_user_was_present_for_is_not_listed(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(
        last_read_minutes_ago=2,
        messages=(("user", "Summarise the report", 11), ("assistant", "The report is ready.", 5)),
    )

    assert await _status(async_client, chat_id) is None


@pytest.mark.asyncio
async def test_a_chat_that_never_recorded_presence_counts_as_read(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(
        last_read_minutes_ago=None,
        messages=(("user", "An old question", 60), ("assistant", "An old answer", 59)),
    )

    assert await _status(async_client, chat_id) is None


@pytest.mark.asyncio
async def test_a_chat_with_a_turn_in_flight_is_running_even_without_a_reply(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(last_read_minutes_ago=1, messages=(("user", "Research competitors", 2),))
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="msg-running")
    try:
        brief = (await _briefs(async_client))[chat_id]
    finally:
        gateway.release_session(chat_id)

    assert brief["status"] == "running"
    assert brief["last_user_prompt"] == "Research competitors"
    assert await _status(async_client, chat_id) is None


@pytest.mark.asyncio
async def test_a_pending_approval_outranks_a_running_turn(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(last_read_minutes_ago=1, messages=(("user", "Delete the old build artifacts", 2),))
    await _add_pending_approval(chat_id)
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="msg-blocked")
    try:
        brief = (await _briefs(async_client))[chat_id]
    finally:
        gateway.release_session(chat_id)

    assert brief["status"] == "waiting_for_approval"
    assert brief["needs_from_user"] == "approval"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phase", "status", "needs"),
    [(RunDigestPhase.ERROR, "error", "error"), (RunDigestPhase.CANCELLED, "stopped", None)],
)
async def test_a_turn_that_failed_while_the_user_was_away_is_listed_without_any_reply(
    async_client: httpx.AsyncClient,
    digest_chats: list[str],
    phase: RunDigestPhase,
    status: str,
    needs: str | None,
) -> None:
    chat_id = await _seed_chat(last_read_minutes_ago=10, messages=(("user", "Run the nightly analysis", 11),))
    digest_chats.append(chat_id)
    RunDigestStore.end_run(chat_id, phase=phase)

    brief = (await _briefs(async_client))[chat_id]

    assert brief["status"] == status
    assert brief["needs_from_user"] == needs
    assert brief["result_preview"] == ""


@pytest.mark.asyncio
async def test_a_failure_leaves_the_inbox_once_the_user_is_back(async_client: httpx.AsyncClient, digest_chats: list[str]) -> None:
    chat_id = await _seed_chat(last_read_minutes_ago=10, messages=(("user", "Run the nightly analysis", 11),))
    digest_chats.append(chat_id)
    RunDigestStore.end_run(chat_id, phase=RunDigestPhase.ERROR)
    assert await _status(async_client, chat_id) == "error"

    assert (await async_client.post(f"/api/v1/chats/{chat_id}/read")).status_code == 200

    assert await _status(async_client, chat_id) is None


@pytest.mark.asyncio
async def test_a_failure_the_user_already_saw_is_not_listed(async_client: httpx.AsyncClient, digest_chats: list[str]) -> None:
    chat_id = await _seed_chat(last_read_minutes_ago=None, messages=(("user", "Run the nightly analysis", 11),))
    digest_chats.append(chat_id)
    RunDigestStore.end_run(chat_id, phase=RunDigestPhase.COMPLETED)

    assert await _status(async_client, chat_id) is None


@pytest.mark.asyncio
async def test_a_system_wakeup_row_is_never_the_prompt(async_client: httpx.AsyncClient) -> None:
    wakeup_id = f"{WAKEUP_MESSAGE_ID_PREFIX}task-1"
    chat_id = await _seed_chat(
        last_read_minutes_ago=10,
        messages=(
            ("user", "Crawl the three sites", 20),
            ("user", "<system_notification type='async_result' task_id='task-1'>done</system_notification>", 6),
            ("assistant", "All three sites are crawled.", 5),
        ),
        message_ids=("user-real", wakeup_id, "assistant-1"),
    )

    brief = (await _briefs(async_client))[chat_id]

    assert brief["last_user_prompt"] == "Crawl the three sites"
    assert brief["result_preview"] == "All three sites are crawled."


@pytest.mark.asyncio
async def test_the_reply_preview_is_bounded_whatever_the_reply_size(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(
        last_read_minutes_ago=10,
        messages=(("user", "Write the long report", 11), ("assistant", "word " * 20_000, 5)),
    )

    preview = str((await _briefs(async_client))[chat_id]["result_preview"])

    assert 0 < len(preview) <= 240
    assert preview.endswith("…")


@pytest.mark.asyncio
async def test_files_and_tools_are_summarised_from_the_unseen_progress_steps(async_client: httpx.AsyncClient) -> None:
    chat_id = await _seed_chat(last_read_minutes_ago=10, messages=(("user", "Fix the bug", 11),))
    async with get_session_factory()() as db:
        db.add(
            Message(
                id=f"msg-{uuid.uuid4().hex[:10]}",
                chat_id=chat_id,
                role="assistant",
                content="Fixed.",
                sent_at=_ago(5),
                sent_timezone="UTC",
                created_at=_ago(5),
                extra_data={
                    "progressSteps": [
                        {"tool_name": "file_edit_tool", "items": [{"path": "src/app.py"}]},
                        {"tool_name": "file_edit_tool", "items": [{"path": "src/app.py"}]},
                        {"tool_name": "shell_tool", "items": [{"command": "pytest"}]},
                    ]
                },
            )
        )
        await db.commit()

    brief = (await _briefs(async_client))[chat_id]

    assert brief["files_touched"] == ["src/app.py"]
    assert brief["tool_counts"] == {"file_edit_tool": 2, "shell_tool": 1}


@pytest.mark.asyncio
async def test_trashed_and_non_web_chats_are_never_listed(async_client: httpx.AsyncClient) -> None:
    unseen = (("user", "Question", 11), ("assistant", "Answer", 5))
    trashed = await _seed_chat(last_read_minutes_ago=10, messages=unseen, deleted=True)
    cron = await _seed_chat(last_read_minutes_ago=10, messages=unseen, source="cron")

    briefs = await _briefs(async_client)

    assert trashed not in briefs
    assert cron not in briefs


@pytest.mark.asyncio
async def test_the_inbox_lists_at_most_twenty_chats(async_client: httpx.AsyncClient) -> None:
    for _ in range(22):
        await _seed_chat(last_read_minutes_ago=10, messages=(("user", "Question", 11), ("assistant", "Answer", 5)))

    assert len(await _briefs(async_client)) == 20


@pytest.mark.asyncio
async def test_marking_a_chat_as_read_clears_it_and_keeps_its_place_in_the_sidebar(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = await _seed_chat(
        last_read_minutes_ago=10,
        messages=(("user", "Summarise the report", 11), ("assistant", "The report is ready.", 5)),
    )
    assert await _status(async_client, chat_id) == "completed"
    async with get_session_factory()() as db:
        updated_before = (await db.execute(select(Chat.updated_at).where(Chat.id == chat_id))).scalar_one()

    response = await async_client.post(f"/api/v1/chats/{chat_id}/read")

    assert response.status_code == 200
    assert await _status(async_client, chat_id) is None
    async with get_session_factory()() as db:
        updated_after = (await db.execute(select(Chat.updated_at).where(Chat.id == chat_id))).scalar_one()
    assert updated_after == updated_before


@pytest.mark.asyncio
async def test_marking_an_unknown_chat_as_read_answers_not_found(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post(f"/api/v1/chats/missing-{uuid.uuid4().hex[:10]}/read")

    assert response.status_code == 404
