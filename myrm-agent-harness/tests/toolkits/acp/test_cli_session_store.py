"""CLI session continuity across process restarts: ``RuntimePool`` + ``CliRuntime`` + a host ``CliSessionStore``.

A CLI backend spawns one process per turn, so the only thing that makes turn N+1 remember turn N is the CLI-native
session id replayed through ``--resume``. Without a store that id lives in memory and dies with the process; with one,
a new pool resumes the conversation. The fake ``claude`` below reproduces the two real Claude Code behaviours the
runtime depends on: a conversation is only found from the directory that created it, and resuming an unknown one
fails fast (exit 1, ``No conversation found``) instead of starting a new conversation.
"""

from __future__ import annotations

import asyncio
import json
import stat
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli_session import CliSessionBook
from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import (
    AcpErrorCode,
    CliSessionRecord,
    CliSessionStore,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLI is a POSIX shebang script")

_FAKE_CLI = """\
#!__PYTHON__
import json, os, sys, time, uuid

here = os.path.dirname(os.path.abspath(__file__))
cwd = os.getcwd()
resume = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else None
sys.stdin.read()
with open(os.path.join(here, "calls.jsonl"), "a") as handle:
    handle.write(json.dumps({"resume": resume, "cwd": cwd}) + "\\n")
if resume is not None and os.path.exists(os.path.join(here, "hang")):
    time.sleep(60)

disk = os.path.join(here, "conversations.jsonl")
known = [json.loads(line) for line in open(disk)] if os.path.exists(disk) else []
if resume is not None and not any(item == {"id": resume, "cwd": cwd} for item in known):
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "session_id": resume}), flush=True)
    sys.stderr.write("No conversation found with session ID: " + resume + "\\n")
    sys.exit(1)

session_id = resume or uuid.uuid4().hex[:8]
if resume is None:
    with open(disk, "a") as handle:
        handle.write(json.dumps({"id": session_id, "cwd": cwd}) + "\\n")
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": session_id}]}}), flush=True)
print(json.dumps({"type": "result", "session_id": session_id}), flush=True)
"""


class _RecordingStore:
    """In-memory ``CliSessionStore`` that logs every operation and can be told to fail one."""

    def __init__(self) -> None:
        self.records: dict[str, CliSessionRecord] = {}
        self.ops: list[tuple[str, str]] = []
        self.failing: set[str] = set()

    async def load(self, session_id: str) -> CliSessionRecord | None:
        self._enter("load", session_id)
        return self.records.get(session_id)

    async def save(self, session_id: str, record: CliSessionRecord) -> None:
        self._enter("save", session_id)
        self.records[session_id] = record

    async def delete(self, session_id: str) -> None:
        self._enter("delete", session_id)
        self.records.pop(session_id, None)

    def _enter(self, op: str, session_id: str) -> None:
        self.ops.append((op, session_id))
        if op in self.failing:
            raise RuntimeError(f"{op} failed")


@dataclass
class _FakeCli:
    claude: Path
    codex: Path
    work_a: Path
    work_b: Path
    calls_file: Path

    @property
    def hang_flag(self) -> Path:
        """While this file exists, a resumed call stays silent until it is killed."""
        return self.calls_file.parent / "hang"

    def resume_args(self) -> list[str | None]:
        if not self.calls_file.exists():
            return []
        return [json.loads(line)["resume"] for line in self.calls_file.read_text().splitlines()]


@pytest.fixture
def fake_cli(tmp_path: Path) -> _FakeCli:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands: dict[str, Path] = {}
    # The basename decides resume support: CliRuntime only resumes sessions for `claude`.
    for name in ("claude", "codex"):
        command = bin_dir / name
        command.write_text(_FAKE_CLI.replace("__PYTHON__", sys.executable))
        command.chmod(command.stat().st_mode | stat.S_IEXEC)
        commands[name] = command
    work_a, work_b = tmp_path / "work-a", tmp_path / "work-b"
    work_a.mkdir()
    work_b.mkdir()
    return _FakeCli(commands["claude"], commands["codex"], work_a, work_b, bin_dir / "calls.jsonl")


@pytest.fixture
async def pools() -> AsyncIterator[list[RuntimePool]]:
    created: list[RuntimePool] = []
    yield created
    for pool in created:
        await pool.close_all()


def _make_pool(
    pools: list[RuntimePool],
    command: Path,
    cwd: Path,
    store: CliSessionStore | None,
    *,
    name: str = "claude",
) -> RuntimePool:
    pool = RuntimePool(max_concurrent=2, cli_session_store=store)
    pool.register(
        name,
        RuntimeConfig(
            backend_type="cli",
            command=str(command),
            args=["-p", "--output-format", "stream-json"],
            permission_mode="safe",
            cwd=str(cwd),
            timeout_seconds=20,
        ),
    )
    pools.append(pool)
    return pool


async def _run_turn(
    pool: RuntimePool, *, name: str = "claude", mode: str = "persistent", session_id: str = "chat-1"
) -> tuple[str, list[RuntimeEvent]]:
    text: list[str] = []
    errors: list[RuntimeEvent] = []
    async for event in pool.run_turn(name, "prompt", session_id=session_id, mode=mode):
        if event.type == RuntimeEventType.TEXT_DELTA:
            text.append(str(event.data.get("content")))
        elif event.type == RuntimeEventType.ERROR:
            errors.append(event)
    return "".join(text), errors


@pytest.mark.asyncio
async def test_a_new_pool_resumes_the_session_a_previous_pool_stored(
    fake_cli: _FakeCli, pools: list[RuntimePool]
) -> None:
    """A server restart builds a new pool; the chat must still pick up where it left off."""
    store = _RecordingStore()
    first_pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)
    first, first_errors = await _run_turn(first_pool)
    await first_pool.close_all()

    second_pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)
    second, second_errors = await _run_turn(second_pool)

    assert not first_errors
    assert not second_errors
    assert first
    assert second == first
    assert fake_cli.resume_args() == [None, first]
    assert store.records == {"chat-1": CliSessionRecord(first, str(fake_cli.work_a))}


@pytest.mark.asyncio
async def test_without_a_store_a_new_pool_starts_a_fresh_session(fake_cli: _FakeCli, pools: list[RuntimePool]) -> None:
    first_pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, None)
    first, _ = await _run_turn(first_pool)
    await first_pool.close_all()

    second_pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, None)
    second, _ = await _run_turn(second_pool)

    assert second != first
    assert fake_cli.resume_args() == [None, None]


@pytest.mark.asyncio
async def test_a_session_stored_for_another_directory_is_not_resumed(
    fake_cli: _FakeCli, pools: list[RuntimePool]
) -> None:
    """Claude Code finds a conversation only from the directory that created it; the chat moved to another folder."""
    store = _RecordingStore()
    in_a = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)
    id_a, _ = await _run_turn(in_a)

    in_b = _make_pool(pools, fake_cli.claude, fake_cli.work_b, store)
    id_b, errors = await _run_turn(in_b)
    resumed_b, _ = await _run_turn(in_b)

    assert not errors
    assert id_b != id_a
    assert resumed_b == id_b
    assert fake_cli.resume_args() == [None, None, id_b]
    assert store.records["chat-1"] == CliSessionRecord(id_b, str(fake_cli.work_b))


@pytest.mark.asyncio
async def test_oneshot_turns_never_touch_the_store(fake_cli: _FakeCli, pools: list[RuntimePool]) -> None:
    """A oneshot review is a throwaway fresh session: it must neither read nor overwrite the chat's stored one."""
    store = _RecordingStore()
    pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)
    first, _ = await _run_turn(pool)
    oneshot, _ = await _run_turn(pool, mode="oneshot", session_id="claude-oneshot-1")
    third, _ = await _run_turn(pool)

    assert oneshot != first
    assert third == first
    assert all(session_id == "chat-1" for _, session_id in store.ops)
    assert store.records == {"chat-1": CliSessionRecord(first, str(fake_cli.work_a))}


@pytest.mark.asyncio
async def test_an_unchanged_session_is_loaded_and_saved_once(fake_cli: _FakeCli, pools: list[RuntimePool]) -> None:
    """Steady state costs no store traffic: the session id is read once and written once, not on every turn."""
    store = _RecordingStore()
    pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)
    for _ in range(3):
        await _run_turn(pool)

    assert store.ops == [("load", "chat-1"), ("save", "chat-1")]


@pytest.mark.asyncio
async def test_store_failures_never_fail_a_turn(fake_cli: _FakeCli, pools: list[RuntimePool]) -> None:
    """A broken store degrades to in-memory continuity, and the unsaved record is retried on the next turn."""
    store = _RecordingStore()
    store.failing = {"load", "save"}
    pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)

    first, first_errors = await _run_turn(pool)
    second, second_errors = await _run_turn(pool)

    assert not first_errors
    assert not second_errors
    assert second == first
    assert fake_cli.resume_args() == [None, first]
    assert [op for op, _ in store.ops].count("save") == 2


@pytest.mark.asyncio
async def test_a_stale_stored_session_is_deleted_and_the_next_turn_starts_fresh(
    fake_cli: _FakeCli, pools: list[RuntimePool]
) -> None:
    """Claude Code expired the conversation: the record must not keep failing every turn after every restart."""
    store = _RecordingStore()
    store.records["chat-1"] = CliSessionRecord("deadbeef", str(fake_cli.work_a))
    pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)

    text, errors = await _run_turn(pool)
    assert not text
    assert [event.data["error"].code for event in errors] == [AcpErrorCode.PROCESS_CRASHED]
    assert errors[0].data["error"].retryable is True
    assert "chat-1" not in store.records

    fresh, fresh_errors = await _run_turn(pool)

    assert not fresh_errors
    assert fake_cli.resume_args() == ["deadbeef", None]
    assert store.records == {"chat-1": CliSessionRecord(fresh, str(fake_cli.work_a))}


@pytest.mark.asyncio
async def test_cancelling_a_resumed_turn_keeps_the_stored_session(fake_cli: _FakeCli, pools: list[RuntimePool]) -> None:
    """Stop pressed before the CLI says anything is not evidence that it forgot the conversation."""
    store = _RecordingStore()
    pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)
    first, _ = await _run_turn(pool)
    fake_cli.hang_flag.touch()

    turn = asyncio.create_task(_run_turn(pool))
    async with asyncio.timeout(20):
        while len(fake_cli.resume_args()) < 2:
            await asyncio.sleep(0.05)
    await pool.cancel("claude", "chat-1")
    await turn
    fake_cli.hang_flag.unlink()

    after_cancel, errors = await _run_turn(pool)

    assert not errors
    assert after_cancel == first
    assert store.records == {"chat-1": CliSessionRecord(first, str(fake_cli.work_a))}
    assert ("delete", "chat-1") not in store.ops


@pytest.mark.asyncio
async def test_commands_without_resume_support_never_touch_the_store(
    fake_cli: _FakeCli, pools: list[RuntimePool]
) -> None:
    store = _RecordingStore()
    pool = _make_pool(pools, fake_cli.codex, fake_cli.work_a, store, name="codex")

    await _run_turn(pool, name="codex")
    await _run_turn(pool, name="codex")

    assert store.ops == []
    assert fake_cli.resume_args() == [None, None]


@pytest.mark.asyncio
async def test_a_dropped_session_is_not_reloaded_from_the_store_in_the_same_process(
    fake_cli: _FakeCli, pools: list[RuntimePool]
) -> None:
    """After a stale drop, the same pool's next turn must not resurrect the id it just deleted."""
    store = _RecordingStore()
    store.records["chat-1"] = CliSessionRecord("deadbeef", str(fake_cli.work_a))
    pool = _make_pool(pools, fake_cli.claude, fake_cli.work_a, store)

    await _run_turn(pool)
    await _run_turn(pool)

    assert fake_cli.resume_args().count("deadbeef") == 1


class TestCliSessionBook:
    def test_memory_is_bounded_and_evicts_the_oldest_record_first(self) -> None:
        book = CliSessionBook("test")
        for index in range(600):
            book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))

        assert len(book) == 512
        assert "s0" not in book
        assert "s599" in book

    def test_overwriting_a_record_at_capacity_evicts_nothing(self) -> None:
        book = CliSessionBook("test")
        for index in range(512):
            book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))
        book.remember("s5", CliSessionRecord("renewed", "/work"))

        assert len(book) == 512
        assert "s0" in book

    @pytest.mark.asyncio
    async def test_a_forgotten_record_is_written_again_when_the_same_record_comes_back(self) -> None:
        """Forgetting empties the store, so persisting an identical record afterwards must not be skipped."""
        store = _RecordingStore()
        book = CliSessionBook("test", store)
        record = CliSessionRecord("cli-1", "/work")
        book.remember("s1", record)
        await book.persist("s1")
        await book.forget("s1")
        assert store.records == {}

        book.remember("s1", record)
        await book.persist("s1")

        assert store.records == {"s1": record}

    @pytest.mark.asyncio
    async def test_an_evicted_record_is_still_loadable_from_the_store(self) -> None:
        store = _RecordingStore()
        store.records["s0"] = CliSessionRecord("cli-0", "/work")
        book = CliSessionBook("test", store)
        await book.resumable("s0", "/work")
        for index in range(1, 600):
            book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))
        assert "s0" not in book

        assert await book.resumable("s0", "/work") == CliSessionRecord("cli-0", "/work")
