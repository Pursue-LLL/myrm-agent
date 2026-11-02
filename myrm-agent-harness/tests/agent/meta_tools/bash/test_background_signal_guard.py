"""A job's group is signalled only while the leader's pid is still the job's, at every signal of a stop.

The group signal and the process table are doubles here: what is under test is which signals a stop sends when
another process takes over the leader's pid at different points of it, so no real process is signalled.
"""

from __future__ import annotations

import asyncio
import itertools
import signal
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background import termination
from myrm_agent_harness.agent.meta_tools.bash._background.consume import BackgroundRegistryEntry
from myrm_agent_harness.agent.meta_tools.bash._background.termination import (
    GroupMember,
    signal_group_if_ours,
    stop_job,
    stop_leftovers,
)
from myrm_agent_harness.utils.os_compat import SIGKILL

_PID = 424242
_LEADER = GroupMember(pid=_PID, start_stamp=100.0)
_SURVIVOR = GroupMember(pid=_PID + 1, start_stamp=200.0)
_GRACE_SECONDS = 0.05

# The pid is looked at right before each signal. ``(looks before the takeover, signals sent)``:
_ESCALATION_OUTCOMES = [
    pytest.param(0, [], id="taken-before-the-first-signal"),
    pytest.param(1, [signal.SIGTERM], id="taken-before-the-escalation"),
    pytest.param(2, [signal.SIGTERM, SIGKILL], id="taken-after-the-last-signal"),
]
# The same, with the survivors the stop reports:
_STOP_OUTCOMES = [
    pytest.param(0, [], (), id="taken-before-the-first-signal"),
    pytest.param(1, [signal.SIGTERM], (), id="taken-before-the-last-signal"),
    pytest.param(2, [signal.SIGTERM, SIGKILL], (_SURVIVOR,), id="taken-after-the-last-signal"),
]


@pytest.fixture
def sent() -> Iterator[list[signal.Signals]]:
    """What the group signal was asked to send; nothing reaches a real process."""
    log: list[signal.Signals] = []
    with patch.object(termination, "kill_spawned_group", lambda _pid, sig: log.append(sig)):
        yield log


@pytest.fixture(autouse=True)
def _short_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(termination, "_REAP_LEADER_SECONDS", _GRACE_SECONDS)
    monkeypatch.setattr(termination, "_CONFIRM_SECONDS", _GRACE_SECONDS)


@pytest.fixture
def group_holds_a_survivor() -> Iterator[None]:
    """The process table shows ``_SURVIVOR`` in the group whenever it is read."""
    with patch.object(termination, "snapshot_group_members", return_value=(_SURVIVOR,)):
        yield


def _takes_over_after(looks: int) -> Callable[[GroupMember | None], bool]:
    """A ``leader_id_reassigned`` that finds the pid taken over from look number ``looks`` on (counting from 0).

    As in the real check, a signal that is checked against no recorded leader never finds a takeover.
    """
    counter = itertools.count()

    def reassigned(leader: GroupMember | None) -> bool:
        look = next(counter)
        return leader is not None and look >= looks

    return reassigned


def _entry(*, leader_exits: bool) -> BackgroundRegistryEntry:
    """A running job as ``stop_job`` reads it: its pid, its recorded leader and the wait for the leader's exit."""

    async def wait() -> int:
        if not leader_exits:
            await asyncio.Event().wait()
        return 0

    entry = SimpleNamespace(info=SimpleNamespace(pid=_PID), leader=_LEADER, proc=SimpleNamespace(wait=wait))
    return cast(BackgroundRegistryEntry, entry)


def test_a_group_is_signalled_while_its_leader_pid_is_the_jobs(sent: list[signal.Signals]) -> None:
    with patch.object(termination, "leader_id_reassigned", return_value=False):
        assert signal_group_if_ours(_PID, _LEADER, SIGKILL) is True

    assert sent == [SIGKILL]


def test_a_group_is_not_signalled_once_another_process_holds_the_leader_pid(sent: list[signal.Signals]) -> None:
    with patch.object(termination, "leader_id_reassigned", return_value=True):
        assert signal_group_if_ours(_PID, _LEADER, SIGKILL) is False

    assert sent == []


def test_a_leader_that_was_never_recorded_is_trusted(sent: list[signal.Signals]) -> None:
    assert signal_group_if_ours(_PID, None, signal.SIGTERM) is True

    assert sent == [signal.SIGTERM]


def test_a_signal_that_fails_at_the_system_is_not_an_error() -> None:
    with patch.object(termination, "kill_spawned_group", side_effect=OSError("no such group")):
        assert signal_group_if_ours(_PID, None, SIGKILL) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("takes_over_after", "expected_sent"), _ESCALATION_OUTCOMES)
async def test_the_escalation_to_sigkill_checks_the_leader_pid_again(
    sent: list[signal.Signals], takes_over_after: int, expected_sent: list[signal.Signals]
) -> None:
    with patch.object(termination, "leader_id_reassigned", _takes_over_after(takes_over_after)):
        survivors = await stop_job(_entry(leader_exits=False), force=False, grace_seconds=_GRACE_SECONDS)

    assert sent == expected_sent
    assert survivors == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProcessLookupError, OSError])
async def test_a_leader_that_cannot_be_waited_for_still_has_its_group_settled(
    sent: list[signal.Signals], error: type[OSError]
) -> None:
    async def wait() -> int:
        raise error

    entry = SimpleNamespace(info=SimpleNamespace(pid=_PID), leader=_LEADER, proc=SimpleNamespace(wait=wait))
    with patch.object(termination, "leader_id_reassigned", return_value=False):
        survivors = await stop_job(cast(BackgroundRegistryEntry, entry), force=False, grace_seconds=_GRACE_SECONDS)

    assert sent == [signal.SIGTERM]
    assert survivors == ()


@pytest.mark.asyncio
@pytest.mark.usefixtures("group_holds_a_survivor")
@pytest.mark.parametrize(("takes_over_after", "expected_sent", "expected_survivors"), _STOP_OUTCOMES)
async def test_the_final_sigkill_of_a_stop_checks_the_leader_pid_again(
    sent: list[signal.Signals],
    takes_over_after: int,
    expected_sent: list[signal.Signals],
    expected_survivors: tuple[GroupMember, ...],
) -> None:
    with patch.object(termination, "leader_id_reassigned", _takes_over_after(takes_over_after)):
        survivors = await stop_job(_entry(leader_exits=True), force=False, grace_seconds=_GRACE_SECONDS)

    assert sent == expected_sent
    assert survivors == expected_survivors


@pytest.mark.asyncio
@pytest.mark.usefixtures("group_holds_a_survivor")
@pytest.mark.parametrize(("takes_over_after", "expected_sent", "expected_survivors"), _STOP_OUTCOMES)
async def test_stopping_what_a_finished_job_left_checks_the_leader_pid_at_every_signal(
    sent: list[signal.Signals],
    takes_over_after: int,
    expected_sent: list[signal.Signals],
    expected_survivors: tuple[GroupMember, ...],
) -> None:
    with patch.object(termination, "leader_id_reassigned", _takes_over_after(takes_over_after)):
        survivors = await stop_leftovers(_PID, (_SURVIVOR,), _LEADER, force=False, grace_seconds=_GRACE_SECONDS)

    assert sent == expected_sent
    assert survivors == expected_survivors


@pytest.mark.asyncio
@pytest.mark.usefixtures("group_holds_a_survivor")
async def test_nothing_is_signalled_for_a_finished_job_with_no_recorded_member(sent: list[signal.Signals]) -> None:
    survivors = await stop_leftovers(_PID, (), _LEADER, force=False, grace_seconds=_GRACE_SECONDS)

    assert sent == []
    assert survivors == ()
