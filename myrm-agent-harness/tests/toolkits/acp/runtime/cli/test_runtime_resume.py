"""How ``CliRuntime`` keeps a conversation going across turns: announce, resume, stale sessions, restarts.

The CLI's own session id is what carries a conversation, and the CLI is the only authority on whether it still
knows one. So the id is stored when the CLI announces it (not when the turn ends), replayed only in the directory
that created it, and replaced — never deleted — once the CLI starts a new conversation in its place.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, CliSessionRecord

from ._fakes import FakeCli, RecordingStore, errors_of, make_runtime, run_turn, statuses_of, text_of, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")

_DEAD = "99999999-0000-4000-8000-000000000000"


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(15):
        while not condition():
            await asyncio.sleep(0.02)


@pytest.fixture
def work(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


class TestClaudeConversation:
    @pytest.mark.asyncio
    async def test_the_announced_session_is_stored_and_resumed_by_the_next_turn(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))

        first = await run_turn(runtime)
        second = await run_turn(runtime)

        session = text_of(first)
        assert session
        assert text_of(second) == session
        assert fake_cli.resume_args() == [None, session]
        assert store.records == {"s1": CliSessionRecord(session, str(work))}

    @pytest.mark.asyncio
    async def test_a_turn_stopped_right_after_the_announcement_still_continues(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        """Stop pressed before the CLI finishes its first turn: the conversation already exists and is kept."""
        store = RecordingStore()
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))
        fake_cli.set_scenario({"hang_after_init": True})
        turn = asyncio.create_task(run_turn(runtime))
        await _until(lambda: "s1" in store.records)

        await runtime.cancel("s1")
        stopped = await asyncio.wait_for(turn, 15)
        fake_cli.set_scenario({})
        resumed = await run_turn(runtime)

        session = store.records["s1"].cli_session_id
        assert [e.data["error"].code for e in errors_of(stopped)] == [AcpErrorCode.CANCELLED]
        assert fake_cli.resume_args() == [None, session]
        assert text_of(resumed) == session

    @pytest.mark.asyncio
    async def test_the_turn_limit_is_not_a_reason_to_forget_the_conversation(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))
        session = text_of(await run_turn(runtime))
        fake_cli.set_scenario({"fail": "max_turns"})

        limited = await run_turn(runtime)
        fake_cli.set_scenario({})
        after = await run_turn(runtime)

        assert [e.data["error"].code for e in errors_of(limited)] == [AcpErrorCode.MAX_TURNS]
        assert fake_cli.resume_args() == [None, session, session]
        assert text_of(after) == session
        assert store.records["s1"].cli_session_id == session

    @pytest.mark.asyncio
    async def test_a_resumed_turn_that_fails_after_announcing_is_not_taken_for_a_forgotten_conversation(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        runtime = make_runtime(fake_cli, store=RecordingStore(), cwd=str(work))
        session = text_of(await run_turn(runtime))
        fake_cli.set_scenario({"text": "", "fail": "crash"})

        events = await run_turn(runtime)

        assert [e.data["error"].code for e in errors_of(events)] == [AcpErrorCode.PROCESS_CRASHED]
        assert statuses_of(events) == ["starting"]
        assert fake_cli.resume_args() == [None, session]

    @pytest.mark.asyncio
    async def test_a_session_stored_by_another_process_is_resumed_after_a_restart(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        session = text_of(await run_turn(make_runtime(fake_cli, store=store, cwd=str(work))))

        restarted = await run_turn(make_runtime(fake_cli, store=store, cwd=str(work)))

        assert text_of(restarted) == session
        assert fake_cli.resume_args() == [None, session]


class TestWorkspaceChange:
    @pytest.mark.asyncio
    async def test_a_session_from_another_directory_is_not_replayed_and_the_user_is_told(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        """Claude finds a conversation only from the directory that created it."""
        work_a, work_b = tmp_path / "a", tmp_path / "b"
        work_a.mkdir()
        work_b.mkdir()
        store = RecordingStore()
        in_a = text_of(await run_turn(make_runtime(fake_cli, store=store, cwd=str(work_a))))

        moved = await run_turn(make_runtime(fake_cli, store=store, cwd=str(work_b)))

        in_b = text_of(moved)
        assert in_b != in_a
        assert statuses_of(moved) == ["starting", "session_workspace_changed"]
        assert not errors_of(moved)
        assert fake_cli.resume_args() == [None, None]
        assert store.records["s1"] == CliSessionRecord(in_b, str(work_b))

    @pytest.mark.asyncio
    async def test_the_new_directory_conversation_is_then_resumed_like_any_other(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        work_a, work_b = tmp_path / "a", tmp_path / "b"
        work_a.mkdir()
        work_b.mkdir()
        store = RecordingStore()
        await run_turn(make_runtime(fake_cli, store=store, cwd=str(work_a)))
        runtime_b = make_runtime(fake_cli, store=store, cwd=str(work_b))
        in_b = text_of(await run_turn(runtime_b))

        again = await run_turn(runtime_b)

        assert text_of(again) == in_b
        assert statuses_of(again) == ["starting"]
        assert fake_cli.resume_args() == [None, None, in_b]


class TestStaleSession:
    @pytest.mark.asyncio
    async def test_a_conversation_the_cli_forgot_is_restarted_in_the_same_turn(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord(_DEAD, str(work))
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))

        events = await run_turn(runtime)

        fresh = text_of(events)
        assert fresh and fresh != _DEAD
        assert not errors_of(events)
        assert statuses_of(events) == ["starting", "session_expired"]
        assert fake_cli.resume_args() == [_DEAD, None]
        assert store.records["s1"] == CliSessionRecord(fresh, str(work))

    @pytest.mark.asyncio
    async def test_the_dead_id_is_never_replayed_again(self, fake_cli: FakeCli, work: Path) -> None:
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord(_DEAD, str(work))
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))

        fresh = text_of(await run_turn(runtime))
        await run_turn(runtime)

        assert fake_cli.resume_args() == [_DEAD, None, fresh]

    @pytest.mark.asyncio
    async def test_the_old_id_stays_until_a_new_conversation_is_really_announced(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        """The retry fails too (say, the CLI is not logged in): nothing proves the old conversation is gone."""
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord(_DEAD, str(work))
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))
        fake_cli.set_scenario([{}, {"fail_before_output": True, "stderr": "not logged in"}])

        events = await run_turn(runtime)

        errors = errors_of(events)
        assert [e.data["error"].code for e in errors] == [AcpErrorCode.PROCESS_CRASHED]
        assert "not logged in" in errors[0].data["error"].message
        assert statuses_of(events) == ["starting", "session_expired"]
        assert fake_cli.resume_args() == [_DEAD, None]
        assert store.records["s1"] == CliSessionRecord(_DEAD, str(work))
        assert all(op != "delete" for op, _ in store.ops)

    @pytest.mark.asyncio
    async def test_a_stopped_resumed_turn_is_not_taken_for_a_forgotten_conversation(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))
        session = text_of(await run_turn(runtime))
        fake_cli.set_scenario({"hang_before_output": True, "exit_on_sigterm": 143})
        turn = asyncio.create_task(run_turn(runtime))
        await _until(lambda: len(fake_cli.calls()) == 2 and runtime.is_alive)

        await runtime.cancel("s1")
        stopped = await asyncio.wait_for(turn, 15)
        fake_cli.set_scenario({})
        after = await run_turn(runtime)

        assert [e.data["error"].code for e in errors_of(stopped)] == [AcpErrorCode.CANCELLED]
        assert "session_expired" not in statuses_of(stopped)
        # One process for the stopped turn: stopping it must not start the fresh retry of a forgotten session.
        assert fake_cli.resume_args() == [None, session, session]
        assert text_of(after) == session
        assert store.records["s1"].cli_session_id == session

    @pytest.mark.asyncio
    async def test_a_malformed_stored_id_is_never_handed_to_the_cli(self, fake_cli: FakeCli, work: Path) -> None:
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord("--dangerously-skip-permissions", str(work))
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))

        events = await run_turn(runtime)

        assert not errors_of(events)
        assert statuses_of(events) == ["starting"]
        assert fake_cli.resume_args() == [None]
        assert store.records["s1"].cli_session_id == text_of(events)


class TestCodexConversation:
    @staticmethod
    def _runtime(fake_cli: FakeCli, work: Path, store: RecordingStore | None = None) -> CliRuntime:
        return make_runtime(fake_cli, "codex", store=store, cwd=str(work), args=["exec", "--json"])

    @pytest.mark.asyncio
    async def test_the_thread_codex_announces_is_continued_with_exec_resume(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        runtime = self._runtime(fake_cli, work, store)

        first = await run_turn(runtime, "one")
        second = await run_turn(runtime, "two")

        thread = text_of(first)
        assert text_of(second) == thread
        assert store.records == {"s1": CliSessionRecord(thread, str(work))}
        argv = fake_cli.calls("codex")[1]["argv"]
        assert isinstance(argv, list)
        assert argv[argv.index("exec") + 1] == "resume"
        assert argv[-2:] == [thread, "two"]
        assert argv.index("--sandbox") < argv.index("exec")

    @pytest.mark.asyncio
    async def test_a_thread_codex_no_longer_has_is_restarted_in_the_same_turn(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord(_DEAD, str(work))

        events = await run_turn(self._runtime(fake_cli, work, store))

        fresh = text_of(events)
        assert fresh != _DEAD
        assert statuses_of(events) == ["starting", "session_expired"]
        assert fake_cli.resume_args("codex") == [_DEAD, None]
        assert store.records["s1"] == CliSessionRecord(fresh, str(work))

    @pytest.mark.asyncio
    async def test_a_malformed_thread_id_is_not_resumed_because_codex_would_silently_start_a_new_thread(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord("thread-1", str(work))

        events = await run_turn(self._runtime(fake_cli, work, store))

        assert statuses_of(events) == ["starting"]
        assert fake_cli.resume_args("codex") == [None]


class TestStore:
    @pytest.mark.asyncio
    async def test_a_session_costs_one_load_and_one_save_however_many_turns_it_lasts(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))

        for _ in range(3):
            await run_turn(runtime)

        assert store.ops == [("load", "s1"), ("save", "s1")]

    @pytest.mark.asyncio
    async def test_a_broken_store_costs_continuity_across_restarts_never_the_turn(
        self, fake_cli: FakeCli, work: Path
    ) -> None:
        store = RecordingStore()
        store.failing = {"load", "save"}
        runtime = make_runtime(fake_cli, store=store, cwd=str(work))

        first = await run_turn(runtime)
        second = await run_turn(runtime)

        assert not errors_of(first)
        assert not errors_of(second)
        assert text_of(second) == text_of(first)
        assert fake_cli.resume_args() == [None, text_of(first)]
        assert [op for op, _ in store.ops].count("save") == 2

    @pytest.mark.asyncio
    async def test_clis_without_resume_support_never_touch_the_store(self, fake_cli: FakeCli, work: Path) -> None:
        store = RecordingStore()
        runtime = make_runtime(fake_cli, "gemini", store=store, cwd=str(work))

        await run_turn(runtime)
        await run_turn(runtime)

        assert store.ops == []
        assert fake_cli.resume_args("gemini") == [None, None]

    @pytest.mark.asyncio
    async def test_without_a_store_a_restart_starts_a_new_conversation(self, fake_cli: FakeCli, work: Path) -> None:
        first = text_of(await run_turn(make_runtime(fake_cli, cwd=str(work))))
        second = text_of(await run_turn(make_runtime(fake_cli, cwd=str(work))))

        assert second != first
        assert fake_cli.resume_args() == [None, None]

    @pytest.mark.asyncio
    async def test_conversations_are_kept_per_session_id(self, fake_cli: FakeCli, work: Path) -> None:
        runtime = make_runtime(fake_cli, cwd=str(work))

        a = text_of(await run_turn(runtime, session_id="chat-a"))
        b = text_of(await run_turn(runtime, session_id="chat-b"))
        again = text_of(await run_turn(runtime, session_id="chat-a"))

        assert a != b
        assert again == a
        assert types_of(await run_turn(runtime, session_id="chat-b"))[-1].value == "done"
