"""A folder that stops answering costs one private thread and a bounded wait, never the app's shared pool."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest

from app.services.instance_archive.auto_backup import folder_guard
from app.services.instance_archive.auto_backup.folder_guard import FolderGuard, FolderUnresponsive, Pulse

TIMEOUT = 0.3
WORKER = "auto-backup-folder"


class Stuck:
    """A call that blocks until released, standing in for a share whose server stopped answering."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self) -> str:
        self.started.set()
        self.release.wait()
        return "late"


@pytest.fixture
def stuck() -> Iterator[Stuck]:
    call = Stuck()
    yield call
    call.release.set()  # a test never leaves a thread blocked behind it


def _workers() -> int:
    return sum(1 for thread in threading.enumerate() if thread.name == WORKER)


def _wait_until(condition: Callable[[], bool], seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(autouse=True)
def _no_worker_left_over() -> None:
    """The workers of earlier tests are released at their teardown; counting starts once they have left."""
    assert _wait_until(lambda: _workers() == 0)


def _give_up_on(guard: FolderGuard, call: Callable[[], object]) -> None:
    try:
        guard.call(call)
    except FolderUnresponsive:
        pass


def test_it_returns_what_the_call_returns() -> None:
    assert FolderGuard(TIMEOUT).call(lambda: 42) == 42


def test_an_error_of_the_call_reaches_the_caller_unchanged() -> None:
    def refuse() -> None:
        raise PermissionError("denied")

    with pytest.raises(PermissionError, match="denied"):
        FolderGuard(TIMEOUT).call(refuse)


def test_a_folder_that_does_not_answer_is_an_os_error_the_caller_gives_up_on_at_the_timeout(stuck: Stuck) -> None:
    started = time.monotonic()
    with pytest.raises(FolderUnresponsive) as refused:
        FolderGuard(TIMEOUT).call(stuck)

    assert isinstance(refused.value, OSError)
    assert TIMEOUT * 0.9 <= time.monotonic() - started < TIMEOUT + 1.0


def _fails_at_once(guard: FolderGuard) -> bool:
    started = time.monotonic()
    with pytest.raises(FolderUnresponsive):
        guard.call(lambda: "never runs")
    return time.monotonic() - started < TIMEOUT / 2


def test_once_the_running_call_is_stuck_later_calls_fail_at_once_and_start_no_thread(stuck: Stuck) -> None:
    guard = FolderGuard(TIMEOUT)
    with pytest.raises(FolderUnresponsive):
        guard.call(stuck)
    # The worker picked the call up a moment after it was submitted, so it has been stuck for longer than the timeout
    # only a moment after the first caller gave up; the next caller may still wait out one timeout of its own.
    assert _wait_until(lambda: _fails_at_once(guard))

    started = time.monotonic()
    for _ in range(50):
        with pytest.raises(FolderUnresponsive):
            guard.call(lambda: "never runs")

    assert time.monotonic() - started < TIMEOUT
    assert _workers() == 1


def test_a_call_that_gave_up_while_waiting_its_turn_never_runs(stuck: Stuck) -> None:
    guard = FolderGuard(TIMEOUT)
    threading.Thread(target=_give_up_on, args=(guard, stuck), daemon=True).start()
    assert stuck.started.wait(2)

    ran: list[str] = []
    with pytest.raises(FolderUnresponsive):
        guard.call(lambda: ran.append("queued"))  # behind a call that is not yet known to be stuck
    stuck.release.set()

    assert _wait_until(lambda: _workers() == 0)
    assert ran == []


def test_the_guard_answers_again_once_the_folder_does(stuck: Stuck) -> None:
    guard = FolderGuard(TIMEOUT)
    with pytest.raises(FolderUnresponsive):
        guard.call(stuck)
    stuck.release.set()

    def answers() -> bool:
        try:
            return guard.call(lambda: "ok") == "ok"
        except FolderUnresponsive:
            return False

    assert _wait_until(answers)


def test_healthy_calls_at_the_same_time_all_succeed() -> None:
    guard = FolderGuard(5.0)
    results: list[int] = []
    lock = threading.Lock()

    def one(index: int) -> None:
        def answer() -> int:
            time.sleep(0.01)
            return index

        value = guard.call(answer)
        with lock:
            results.append(value)

    threads = [threading.Thread(target=one, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert sorted(results) == list(range(20))


def test_the_worker_is_a_daemon_so_a_stuck_folder_cannot_keep_the_process_from_closing(stuck: Stuck) -> None:
    guard = FolderGuard(TIMEOUT)
    with pytest.raises(FolderUnresponsive):
        guard.call(stuck)

    workers = [thread for thread in threading.enumerate() if thread.name == WORKER]
    assert workers
    assert all(thread.daemon for thread in workers)


def test_the_worker_leaves_when_there_is_nothing_left_to_run() -> None:
    guard = FolderGuard(TIMEOUT)
    assert guard.call(lambda: "done") == "done"

    assert _wait_until(lambda: _workers() == 0)


def _stalls_after(sign_of_life: int, release: threading.Event, last: list[float]) -> Callable[[Pulse], None]:
    """An operation that reports progress ``sign_of_life`` times, then blocks until released."""

    def operation(pulse: Pulse) -> None:
        for _ in range(sign_of_life):
            time.sleep(TIMEOUT / 3)
            pulse.progress()
        last.append(time.monotonic())
        release.wait()

    return operation


def test_a_call_that_keeps_reporting_progress_is_waited_for_past_the_timeout() -> None:
    def slow_but_alive(pulse: Pulse) -> str:
        for _ in range(8):
            time.sleep(TIMEOUT / 3)
            pulse.progress()
        return "done"

    started = time.monotonic()

    assert FolderGuard(TIMEOUT).call_progressing(slow_but_alive) == "done"
    assert time.monotonic() - started > TIMEOUT * 2


def test_a_call_that_stops_reporting_is_given_up_on_a_timeout_after_its_last_sign_of_life() -> None:
    release, last = threading.Event(), []
    try:
        with pytest.raises(FolderUnresponsive) as refused:
            FolderGuard(TIMEOUT).call_progressing(_stalls_after(3, release, last))
        gave_up = time.monotonic()
    finally:
        release.set()

    assert isinstance(refused.value, OSError)
    assert TIMEOUT * 0.9 <= gave_up - last[0] < TIMEOUT + 1.0


def test_a_call_given_up_on_is_told_so_at_its_next_report() -> None:
    release, told = threading.Event(), []

    def operation(pulse: Pulse) -> None:
        pulse.progress()
        release.wait()
        try:
            pulse.progress()
        except FolderUnresponsive:
            told.append("given up on")

    try:
        with pytest.raises(FolderUnresponsive):
            FolderGuard(TIMEOUT).call_progressing(operation)
    finally:
        release.set()

    assert _wait_until(lambda: told == ["given up on"])


def test_once_a_progressing_call_stopped_reporting_later_calls_of_either_kind_fail_at_once() -> None:
    guard, release = FolderGuard(TIMEOUT), threading.Event()
    try:
        with pytest.raises(FolderUnresponsive):
            guard.call_progressing(_stalls_after(0, release, []))

        started = time.monotonic()
        for _ in range(20):
            with pytest.raises(FolderUnresponsive):
                guard.call(lambda: "never runs")
            with pytest.raises(FolderUnresponsive):
                guard.call_progressing(lambda _: "never runs")

        assert time.monotonic() - started < TIMEOUT
        assert _workers() == 1
    finally:
        release.set()


def test_an_error_of_a_progressing_call_reaches_the_caller_unchanged() -> None:
    def refuse(_: Pulse) -> None:
        raise PermissionError("denied")

    with pytest.raises(PermissionError, match="denied"):
        FolderGuard(TIMEOUT).call_progressing(refuse)


def test_a_pause_of_the_waiting_thread_itself_is_not_taken_for_a_stall(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine that sleeps stops every thread at once; where the clock counts that time, the folder looks silent."""
    skew = [0.0]
    monkeypatch.setattr(folder_guard, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + skew[0]))
    release, begun, outcome = threading.Event(), threading.Event(), []

    def operation(pulse: Pulse) -> str:
        begun.set()
        release.wait()
        pulse.progress()
        return "done"

    def caller() -> None:
        try:
            outcome.append(FolderGuard(TIMEOUT).call_progressing(operation))
        except FolderUnresponsive:
            outcome.append("given up")

    thread = threading.Thread(target=caller)
    thread.start()
    assert begun.wait(2)
    skew[0] += 3600  # the machine slept for an hour
    time.sleep(TIMEOUT / 3)
    release.set()
    thread.join(5)

    assert outcome == ["done"]
