"""CLI session continuity across process restarts: ``RuntimePool`` + ``CliRuntime`` + a host ``CliSessionStore``.

A CLI backend spawns one process per turn, so the only thing that makes turn N+1 remember turn N is the CLI-native
session id replayed through ``--resume``. Without a store that id lives in memory and dies with the process; with one,
a new pool resumes the conversation. The scripted ``claude`` reproduces the Claude Code behaviours the runtime
depends on (see ``_fakes``): a conversation is only found from the directory that created it, and resuming an
unknown one fails fast instead of starting a new conversation.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import CliSessionRecord, CliSessionStore, RuntimeConfig, RuntimeEvent

from ._fakes import FakeCli, RecordingStore, errors_of, statuses_of, text_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")

_DEAD = "99999999-0000-4000-8000-000000000000"


@pytest.fixture
def work(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


@pytest.fixture
async def pools() -> AsyncIterator[list[RuntimePool]]:
    created: list[RuntimePool] = []
    yield created
    for pool in created:
        await pool.close_all()


def _make_pool(pools: list[RuntimePool], fake_cli: FakeCli, cwd: Path, store: CliSessionStore | None) -> RuntimePool:
    pool = RuntimePool(max_concurrent=2, cli_session_store=store)
    pool.register(
        "claude",
        RuntimeConfig(
            backend_type="cli",
            command=str(fake_cli.command("claude")),
            args=["-p", "--output-format", "stream-json"],
            permission_mode="safe",
            cwd=str(cwd),
            timeout_seconds=20,
        ),
    )
    pools.append(pool)
    return pool


async def _run_turn(pool: RuntimePool, *, mode: str = "persistent", session_id: str = "chat-1") -> list[RuntimeEvent]:
    return [e async for e in pool.run_turn("claude", "prompt", session_id=session_id, mode=mode)]


@pytest.mark.asyncio
async def test_a_new_pool_resumes_the_session_a_previous_pool_stored(
    fake_cli: FakeCli, pools: list[RuntimePool], work: Path
) -> None:
    """A server restart builds a new pool; the chat must still pick up where it left off."""
    store = RecordingStore()
    first_pool = _make_pool(pools, fake_cli, work, store)
    first = await _run_turn(first_pool)
    await first_pool.close_all()

    second = await _run_turn(_make_pool(pools, fake_cli, work, store))

    assert not errors_of(first)
    assert not errors_of(second)
    assert text_of(second) == text_of(first)
    assert fake_cli.resume_args() == [None, text_of(first)]
    assert store.records == {"chat-1": CliSessionRecord(text_of(first), str(work))}


@pytest.mark.asyncio
async def test_without_a_store_a_new_pool_starts_a_fresh_session(
    fake_cli: FakeCli, pools: list[RuntimePool], work: Path
) -> None:
    first_pool = _make_pool(pools, fake_cli, work, None)
    first = text_of(await _run_turn(first_pool))
    await first_pool.close_all()

    second = text_of(await _run_turn(_make_pool(pools, fake_cli, work, None)))

    assert second != first
    assert fake_cli.resume_args() == [None, None]


@pytest.mark.asyncio
async def test_oneshot_turns_never_touch_the_store(fake_cli: FakeCli, pools: list[RuntimePool], work: Path) -> None:
    """A oneshot review is a throwaway fresh session: it must neither read nor overwrite the chat's stored one."""
    store = RecordingStore()
    pool = _make_pool(pools, fake_cli, work, store)
    first = text_of(await _run_turn(pool))
    oneshot = text_of(await _run_turn(pool, mode="oneshot", session_id="claude-oneshot-1"))
    third = text_of(await _run_turn(pool))

    assert oneshot != first
    assert third == first
    assert all(session_id == "chat-1" for _, session_id in store.ops)
    assert store.records == {"chat-1": CliSessionRecord(first, str(work))}


@pytest.mark.asyncio
async def test_a_stale_stored_session_is_restarted_in_the_same_turn_and_replaced(
    fake_cli: FakeCli, pools: list[RuntimePool], work: Path
) -> None:
    """The CLI forgot the conversation: the user's turn still runs, and the record never fails a turn again."""
    store = RecordingStore()
    store.records["chat-1"] = CliSessionRecord(_DEAD, str(work))
    pool = _make_pool(pools, fake_cli, work, store)

    stale = await _run_turn(pool)
    next_turn = await _run_turn(pool)

    assert not errors_of(stale)
    assert statuses_of(stale) == ["starting", "session_expired"]
    assert text_of(next_turn) == text_of(stale)
    assert fake_cli.resume_args() == [_DEAD, None, text_of(stale)]
    assert store.records["chat-1"] == CliSessionRecord(text_of(stale), str(work))
